"""Forecast runs: create, execute in the background, and read results."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError, InvalidReferenceError, NotFoundError
from app.db.tenancy import shop_session
from app.models import DailySales, Forecast, ForecastRun, ModelEvaluation, Product, User
from app.models.enums import EvaluationPeriod, RunStatus
from app.db.tenancy import current_shop_id
from app.services import sales as sales_service
from app.services.forecast_engine import (
    ASSUMPTIONS, MODELS, ForecastUnavailable, forecast_matrix, load_context, model_file, model_is_current,
)

logger = logging.getLogger("app.forecasting")
MODEL_VERSION = {"random_forest_v1": "shop-v1", "moving_avg_28": "baseline"}


def last_sales_date(db: Session) -> date:
    last = db.scalar(select(func.max(DailySales.sales_date)))
    if last is None:
        raise AppError("No sales history in the database")
    return last


def holdout_wape(db: Session) -> dict[str, float]:
    """WAPE of each model on the shop's last 28 days, held back when its forest was trained (all items, 28 days)."""
    rows = db.execute(select(ModelEvaluation.model_name, ModelEvaluation.wape).where(
        ModelEvaluation.period == EvaluationPeriod.TEST, ModelEvaluation.horizon_days == 28,
        ModelEvaluation.demand_class == "all", ModelEvaluation.wape.is_not(None))).all()
    return {name: float(wape) for name, wape in rows}


MODEL_SHORT = {"random_forest_v1": "this shop's Random Forest", "moving_avg_28": "the 28-day moving average"}


def class_scores(db: Session) -> dict[str, dict[str, tuple[float, float]]]:
    """Per demand pattern and model, (sum of absolute errors, sum of actual units) on the held-back 28 days.
    Both are recovered from the stored scores: errors = MAE x observations, actuals = errors / WAPE."""
    rows = db.execute(select(ModelEvaluation.model_name, ModelEvaluation.demand_class, ModelEvaluation.mae,
                             ModelEvaluation.n_observations, ModelEvaluation.wape).where(
        ModelEvaluation.period == EvaluationPeriod.TEST, ModelEvaluation.horizon_days == 28,
        ModelEvaluation.demand_class != "all", ModelEvaluation.model_name.in_(MODEL_VERSION))).all()
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for model, cls, mae, n, wape in rows:
        if mae is None or n is None or wape is None or float(wape) <= 0:
            continue
        errors = float(mae) * n
        out.setdefault(cls, {})[model] = (errors, errors / float(wape))
    return out


def choose_auto(db: Session) -> dict:
    """What 'auto' runs: {model, reason, by_class, combined_wape}.

    The main model is the shop's own forest if it is trained, current AND was more accurate than the 28-day
    moving average on the held-back days; otherwise the moving average. When the forest is available, each demand
    pattern (smooth, erratic, intermittent, lumpy) then uses whichever of the two was more accurate for that pattern,
    so for example rarely-sold lumpy items can use the moving average while everyday items use the forest.
    `by_class` lists only the patterns that differ from the main model.
    """
    path = model_file(current_shop_id(db))
    if not path.exists():
        return {"model": "moving_avg_28", "by_class": {}, "combined_wape": None,
                "reason": "Auto: 28-day moving average, because this shop's Random Forest is not trained yet."}
    if not model_is_current(path):
        return {"model": "moving_avg_28", "by_class": {}, "combined_wape": None,
                "reason": ("Auto: 28-day moving average, because this shop's Random Forest was trained before "
                           "the festival features were added and needs retraining.")}
    wape = holdout_wape(db)
    rf, ma = wape.get("random_forest_v1"), wape.get("moving_avg_28")
    main = "moving_avg_28" if rf is not None and ma is not None and rf > ma else "random_forest_v1"

    scores = class_scores(db)
    by_class, errors, actual = {}, 0.0, 0.0
    for cls, models in sorted(scores.items()):
        if len(models) < 2:
            continue
        best = min(models, key=lambda m: models[m][0])
        if best != main and models[best][0] < models[main][0]:
            by_class[cls] = best
        e, a = models[by_class.get(cls, main)]
        errors, actual = errors + e, actual + a
    combined = errors / actual if by_class and actual > 0 else None

    if by_class:
        others = sorted({m for m in by_class.values()})
        names = list(by_class)
        patterns = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        reason = (f"Auto: {MODEL_SHORT[main]} for most products, and {' and '.join(MODEL_SHORT[m] for m in others)} for "
                  f"{patterns} products, where it was more accurate on the last 28 days")
        if combined is not None and rf is not None and ma is not None:
            reason += (f" (combined error {combined:.1%}, against {rf:.1%} for the forest alone and "
                       f"{ma:.1%} for the moving average)")
        return {"model": main, "by_class": by_class, "combined_wape": combined, "reason": reason + "."}
    if main == "moving_avg_28":
        return {"model": main, "by_class": {}, "combined_wape": None,
                "reason": (f"Auto: 28-day moving average, because it was more accurate than this shop's "
                           f"Random Forest on the last 28 days (error {ma:.0%} vs {rf:.0%}).")}
    detail = f" (error {rf:.0%} vs {ma:.0%} for the moving average)" if rf is not None and ma is not None else ""
    return {"model": main, "by_class": {}, "combined_wape": None,
            "reason": f"Auto: this shop's Random Forest, the more accurate model on the last 28 days{detail}."}


def choose_model(db: Session, model_name: str) -> tuple[str, str | None]:
    """(main model, reason). See choose_auto for what 'auto' means."""
    if model_name != "auto":
        return model_name, None
    choice = choose_auto(db)
    return choice["model"], choice["reason"]


def mix_by_class(main: np.ndarray, alternatives: dict[str, np.ndarray], product_ids: np.ndarray,
                 classes: dict[int, str | None], by_class: dict[str, str]) -> tuple[np.ndarray, dict[str, int]]:
    """Replace the rows of products whose demand pattern uses another model. Returns the values and how many
    products each model forecast (main model under the key 'main')."""
    values = main.copy()
    used = {"main": 0, **{m: 0 for m in alternatives}}
    for i, pid in enumerate(product_ids):
        model = by_class.get(classes.get(int(pid)) or "unknown")
        if model in alternatives:
            values[i] = alternatives[model][i]
            used[model] += 1
        else:
            used["main"] += 1
    return values, used


MIN_RECORDED_DAYS_FOR_FOREST = 14     # of the 28 days before the origin; the forest's recent-sales features need them


def create_run(db: Session, *, model_name: str, horizon_days: int, origin_date: date | None, user: User) -> ForecastRun:
    default_origin = last_sales_date(db) + timedelta(days=1)
    origin = origin_date or default_origin
    if origin > default_origin:
        raise AppError(f"Origin must be on or before {default_origin} (the day after the last sales data)")
    choice = choose_auto(db) if model_name == "auto" else {"model": model_name, "reason": None, "by_class": {}}
    if model_name == "auto" and choice["model"] != "moving_avg_28":
        recorded = sales_service.coverage(db, through=origin - timedelta(days=1))["recorded_days"]
        if recorded < MIN_RECORDED_DAYS_FOR_FOREST:
            choice = {"model": "moving_avg_28", "by_class": {}, "combined_wape": None,
                      "reason": (f"Auto: 28-day moving average, because only {recorded} of the 28 days before the "
                                 "forecast have sales recorded, too few for the Random Forest's recent-sales "
                                 "features. The moving average uses the last 28 days that were recorded.")}
    model_name, reason = choice["model"], choice["reason"]
    mixing = {"model_by_class": choice["by_class"], "combined_wape_28d": choice["combined_wape"]} if choice["by_class"] else {}
    if model_name not in MODELS:
        raise InvalidReferenceError(f"Unknown model '{model_name}'. Choose from: {', '.join(MODELS)}")
    run = ForecastRun(model_name=model_name, model_version=MODEL_VERSION[model_name], origin_date=origin,
                      horizon_days=horizon_days, status=RunStatus.PENDING, created_by=user.id,
                      params={"assumptions": ASSUMPTIONS, "history_ends": str(origin - timedelta(days=1)),
                              **({"model_choice": reason} if reason else {}), **mixing})
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_run(session_factory: sessionmaker[Session], shop_id: int, run_id: int) -> None:
    """Background job: compute and store the forecasts, recording success or failure on the run."""
    with shop_session(session_factory, shop_id) as db:
        run = db.get(ForecastRun, run_id)
        run.status = RunStatus.RUNNING
        db.commit()
        try:
            ctx = load_context(db, through=run.origin_date + timedelta(days=run.horizon_days - 1))
            values = forecast_matrix(ctx, run.model_name, run.origin_date, run.horizon_days)
            by_class = (run.params or {}).get("model_by_class") or {}
            used = None
            if by_class:
                alternatives = {m: forecast_matrix(ctx, m, run.origin_date, run.horizon_days) for m in set(by_class.values())}
                classes = dict(db.execute(select(Product.id, Product.demand_class)).all())
                values, used = mix_by_class(values, alternatives, ctx.product_ids, classes, by_class)
            db.execute(insert(Forecast), [
                {"shop_id": shop_id, "forecast_run_id": run.id, "product_id": int(pid), "horizon": h + 1,
                 "forecast_date": run.origin_date + timedelta(days=h),
                 "predicted_units": Decimal(str(round(float(values[i, h]), 3)))}
                for i, pid in enumerate(ctx.product_ids) for h in range(run.horizon_days)
            ])
            run.metrics = {"products": int(len(ctx.product_ids)), "total_units": round(float(values.sum()), 1),
                           **validation_summary(db, run.model_name)}
            if used is not None:
                combined = (run.params or {}).get("combined_wape_28d")
                run.metrics = {**run.metrics, "products_by_model": {run.model_name: used.pop("main"), **used},
                               **({"test_wape_28d": combined} if combined is not None else {})}
            run.status = RunStatus.COMPLETED
        except (ForecastUnavailable, AppError) as exc:
            db.rollback()
            run = db.get(ForecastRun, run_id)
            run.status, run.error_message = RunStatus.FAILED, str(exc)
        except Exception as exc:   # record unexpected failures instead of losing them
            logger.exception("Forecast run %s failed", run_id)
            db.rollback()
            run = db.get(ForecastRun, run_id)
            run.status, run.error_message = RunStatus.FAILED, f"Unexpected error: {type(exc).__name__}"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()


def validation_summary(db: Session, model_name: str) -> dict:
    """Scores on the last 28 days held back during training, for this model, all items, 28-day horizon."""
    row = db.scalar(select(ModelEvaluation).where(
        ModelEvaluation.model_name == model_name, ModelEvaluation.period == EvaluationPeriod.TEST,
        ModelEvaluation.horizon_days == 28, ModelEvaluation.demand_class == "all"))
    if row is None:
        return {}
    return {"test_wape_28d": float(row.wape), "test_bias_pct_28d": float(row.bias_pct)}


def get_run(db: Session, run_id: int) -> ForecastRun:
    run = db.get(ForecastRun, run_id)
    if run is None:
        raise NotFoundError(f"Forecast run {run_id} not found")
    return run


def list_runs(db: Session, limit: int = 50) -> list[ForecastRun]:
    return list(db.scalars(select(ForecastRun).order_by(ForecastRun.created_at.desc(), ForecastRun.id.desc())
                           .limit(limit)))


def latest_completed_run(db: Session, model_name: str | None = None) -> ForecastRun | None:
    query = select(ForecastRun).where(ForecastRun.status == RunStatus.COMPLETED)
    if model_name:
        query = query.where(ForecastRun.model_name == model_name)
    return db.scalar(query.order_by(ForecastRun.id.desc()).limit(1))


def product_forecast(db: Session, product_id: int, run_id: int | None, history_days: int = 56) -> dict:
    """Recent actual sales plus the forecast for one product, kept in separate lists."""
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    run = get_run(db, run_id) if run_id else latest_completed_run(db)
    if run is None:
        raise NotFoundError("No completed forecast run yet")
    if run.status != RunStatus.COMPLETED:
        raise AppError(f"Forecast run {run.id} is {run.status.value}")
    points = db.execute(select(Forecast.forecast_date, Forecast.horizon, Forecast.predicted_units).where(
        Forecast.forecast_run_id == run.id, Forecast.product_id == product_id).order_by(Forecast.forecast_date)).all()
    end = run.origin_date + timedelta(days=run.horizon_days - 1)
    actual = db.execute(select(DailySales.sales_date, DailySales.units, DailySales.is_available).where(
        DailySales.product_id == product_id,
        DailySales.sales_date.between(run.origin_date - timedelta(days=history_days), end),
    ).order_by(DailySales.sales_date)).all()
    return {
        "product_id": product_id, "sku": product.sku, "run": run,
        "history": [{"date": d, "units": u, "is_available": a} for d, u, a in actual if d < run.origin_date],
        # Actuals inside the forecast window exist only for back-dated runs (useful for checking accuracy).
        "actual_in_window": [{"date": d, "units": u, "is_available": a} for d, u, a in actual if d >= run.origin_date],
        "forecast": [{"date": d, "horizon": h, "predicted_units": float(p)} for d, h, p in points],
        "total_forecast": round(sum(float(p) for _, _, p in points), 2),
    }


def evaluations(db: Session, period: EvaluationPeriod | None, horizon_days: int | None) -> list[ModelEvaluation]:
    query = select(ModelEvaluation)
    if period:
        query = query.where(ModelEvaluation.period == period)
    if horizon_days:
        query = query.where(ModelEvaluation.horizon_days == horizon_days)
    return list(db.scalars(query.order_by(ModelEvaluation.period, ModelEvaluation.horizon_days,
                                          ModelEvaluation.demand_class, ModelEvaluation.model_name)))
