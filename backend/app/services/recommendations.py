"""Reorder recommendation runs: apply the tested engine (ml/inventory/recommend.py)
to every active product using a stored forecast run and current stock.

Safety stock uses the forecast model's MEASURED past errors (Phase 4 finding):
  1. Backtest the same model at up to 16 weekly origins whose whole protection
     period ended before the forecast origin.
  2. >= 8 complete periods for the item: RMSE of its protection-period errors.
  3. Otherwise >= 14 daily errors: daily RMSE with the sqrt(days) rule.
  4. Otherwise: "insufficient data" (no recommendation is invented).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import AppSetting, Forecast, ForecastRun, Product, RecommendationRun, ReorderRecommendation, User
from app.models.enums import ReviewStatus, RiskCategory, RunStatus
from app.services import inventory
from app.services.forecast_engine import ForecastContext, forecast_matrix, load_context
from app.services.forecasting import latest_completed_run
from ml.features.build import MIN_HISTORY_DAYS
from ml.inventory import formulas as f
from ml.inventory.recommend import ItemState, PolicySettings, insufficient, recommend

logger = logging.getLogger("app.recommendations")
ERROR_ORIGINS = 16
POLICY_FIELDS = {fld.name for fld in fields(PolicySettings)}
RISK_ORDER = {RiskCategory.CRITICAL: 0, RiskCategory.REORDER_SOON: 1, RiskCategory.EXCESS: 2,
              RiskCategory.INSUFFICIENT: 3, RiskCategory.HEALTHY: 4}


# ---------------------------------------------------------------- policy

def policy_settings(db: Session, overrides: dict[str, Any] | None = None) -> PolicySettings:
    """Stored defaults (app_settings.policy_defaults), then any per-run overrides."""
    stored = db.get(AppSetting, "policy_defaults")
    values = {k: v for k, v in (stored.value if stored else {}).items() if k in POLICY_FIELDS}
    values.update({k: v for k, v in (overrides or {}).items() if k in POLICY_FIELDS and v is not None})
    return PolicySettings(**values)


# ---------------------------------------------------------------- runs

def create_run(db: Session, *, forecast_run_id: int | None, overrides: dict[str, Any], user: User) -> RecommendationRun:
    forecast_run = db.get(ForecastRun, forecast_run_id) if forecast_run_id else latest_completed_run(db)
    if forecast_run is None:
        raise NotFoundError("No completed forecast run; generate a forecast first")
    if forecast_run.status != RunStatus.COMPLETED:
        raise ConflictError(f"Forecast run {forecast_run.id} is {forecast_run.status.value}, not completed")
    policy = policy_settings(db, overrides)
    run = RecommendationRun(forecast_run_id=forecast_run.id, policy_settings=asdict(policy),
                            status=RunStatus.PENDING, created_by=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def error_sigmas(ctx: ForecastContext, model_name: str, origin, protection: np.ndarray
                 ) -> tuple[list[float | None], list[float | None]]:
    """Per item: (measured protection-period sigma, daily error RMSE) from past backtests."""
    max_p = int(protection.max())
    origin_d = ctx.d_num(origin)
    starts = [origin_d - max_p - 7 * k for k in range(ERROR_ORIGINS)]
    starts = [s for s in starts if s - 1 >= MIN_HISTORY_DAYS]
    n = len(ctx.panel.item_ids)
    period_err: list[list[float]] = [[] for _ in range(n)]
    daily_err: list[list[float]] = [[] for _ in range(n)]
    for start in starts:
        fc = forecast_matrix(ctx, model_name, ctx.date_of(start), max_p)
        actual = ctx.panel.sales[:, start - 1: start - 1 + max_p]
        closed = ~ctx.open_day[start - 1: start - 1 + max_p]
        actual = np.where(closed[None, :], 0.0, actual)        # closed day: no demand, not missing
        for i in range(n):
            p = int(protection[i])
            a, fi = actual[i, :p], fc[i, :p]
            known = ~np.isnan(a)
            daily_err[i].extend((fi[known] - a[known]).tolist())
            if known.all():                                    # only complete periods count
                period_err[i].append(float(fi.sum() - a.sum()))
    period_sigma = [f.period_sigma_from_errors(np.array(e)) for e in period_err]
    daily_sigma = [float(np.sqrt(np.mean(np.square(e)))) if len(e) >= 14 else None for e in daily_err]
    return period_sigma, daily_sigma


def execute_run(session_factory: sessionmaker[Session], run_id: int) -> None:
    with session_factory() as db:
        run = db.get(RecommendationRun, run_id)
        run.status = RunStatus.RUNNING
        db.commit()
        try:
            count = _compute(db, run)
            run.status = RunStatus.COMPLETED
            logger.info("Recommendation run %s: %s products", run_id, count)
        except Exception as exc:
            logger.exception("Recommendation run %s failed", run_id)
            db.rollback()
            run = db.get(RecommendationRun, run_id)
            run.status = RunStatus.FAILED
            run.error_message = str(exc) if isinstance(exc, AppError) else f"Unexpected error: {type(exc).__name__}"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()


def _compute(db: Session, run: RecommendationRun) -> int:
    forecast_run = db.get(ForecastRun, run.forecast_run_id)
    policy = PolicySettings(**run.policy_settings)
    horizon = forecast_run.horizon_days

    forecasts: dict[int, np.ndarray] = {}
    for pid, h, value in db.execute(select(Forecast.product_id, Forecast.horizon, Forecast.predicted_units)
                                    .where(Forecast.forecast_run_id == forecast_run.id)):
        forecasts.setdefault(pid, np.zeros(horizon))[h - 1] = float(value)

    stock_rows, _ = inventory.list_stock(db, page=1, page_size=100_000)
    stock = {r["product_id"]: r for r in stock_rows}
    products = db.scalars(select(Product).where(Product.is_active.is_(True))
                          .options(joinedload(Product.supplier))).all()

    ctx = load_context(db, through=forecast_run.origin_date)
    row_of = {int(pid): i for i, pid in enumerate(ctx.product_ids)}
    lead_of = {p.id: p.effective_lead_time_days or 0 for p in products}
    protection = np.array([lead_of.get(int(pid), 0) for pid in ctx.product_ids]) + policy.review_period_days
    period_sigma, daily_sigma = error_sigmas(ctx, forecast_run.model_name, forecast_run.origin_date,
                                             np.minimum(protection, horizon))

    records = []
    for product in products:
        s = stock.get(product.id, {"on_hand": 0, "on_order": 0, "backorders": 0})
        lead_time = product.effective_lead_time_days
        state = ItemState(sku=product.sku, name=product.name, on_hand=s["on_hand"], on_order=s["on_order"],
                          backorders=s["backorders"], lead_time_days=lead_time or 0,
                          unit_cost=float(product.unit_cost) if product.unit_cost is not None else None,
                          min_order_qty=product.min_order_qty, pack_size=product.pack_size,
                          demand_class=product.demand_class)
        i = row_of.get(product.id)
        method = None
        if lead_time is None:
            rec = insufficient(state, "no supplier lead time")
        elif product.id not in forecasts or i is None:
            rec = insufficient(state, "no forecast for this product (no sales history)")
        elif lead_time + policy.review_period_days > horizon:
            rec = insufficient(state, f"forecast horizon {horizon} days is shorter than the "
                                      f"{lead_time + policy.review_period_days}-day protection period")
        else:
            rec = recommend(state, forecasts[product.id], daily_sigma[i], policy, period_sigma=period_sigma[i])
            method = ("measured protection-period forecast errors" if period_sigma[i] is not None
                      else "daily forecast errors x sqrt(days)" if daily_sigma[i] is not None else None)
        records.append(_to_row(run.id, product.id, rec, method))
    db.add_all(records)
    db.flush()
    return len(records)


def _num(value: float | None, places: int = 3) -> Decimal | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return Decimal(str(round(float(value), places)))


def _to_row(run_id: int, product_id: int, rec, sigma_method: str | None) -> ReorderRecommendation:
    warnings = list(rec.warnings)
    if sigma_method:
        warnings.append(f"Safety stock sized from {sigma_method}")
    return ReorderRecommendation(
        recommendation_run_id=run_id, product_id=product_id, on_hand=_num(rec.on_hand),
        inventory_position=_num(rec.inventory_position), lead_time_days=rec.lead_time_days,
        forecast_lead_time_demand=_num(rec.forecast_lead_time_demand),
        forecast_protection_demand=_num(rec.forecast_protection_demand),
        safety_stock=_num(rec.safety_stock), reorder_point=_num(rec.reorder_point),
        order_up_to=_num(rec.order_up_to), suggested_qty=rec.suggested_qty,
        estimated_order_cost=_num(rec.estimated_order_cost, 2), stockout_probability=_num(rec.stockout_probability, 4),
        days_of_cover=_num(rec.days_of_cover, 1), risk_category=RiskCategory(rec.risk_category),
        explanation=rec.explanation, warnings={"messages": warnings},
    )


# ---------------------------------------------------------------- reading and review

def get_run(db: Session, run_id: int) -> RecommendationRun:
    run = db.get(RecommendationRun, run_id)
    if run is None:
        raise NotFoundError(f"Recommendation run {run_id} not found")
    return run


def list_runs(db: Session, limit: int = 50) -> list[RecommendationRun]:
    return list(db.scalars(select(RecommendationRun).order_by(RecommendationRun.id.desc()).limit(limit)))


def run_summary(db: Session, run_id: int) -> dict[str, Any]:
    rows = db.execute(select(ReorderRecommendation.risk_category, func.count(),
                             func.sum(ReorderRecommendation.estimated_order_cost))
                      .where(ReorderRecommendation.recommendation_run_id == run_id)
                      .group_by(ReorderRecommendation.risk_category)).all()
    return {"counts": {r.value: n for r, n, _ in rows},
            "total_suggested_order_cost": float(sum((c or 0) for _, _, c in rows))}


SORTS = {"risk": None, "sku": Product.sku, "suggested_qty": ReorderRecommendation.suggested_qty,
         "estimated_order_cost": ReorderRecommendation.estimated_order_cost,
         "days_of_cover": ReorderRecommendation.days_of_cover}


def list_recommendations(db: Session, *, run_id: int | None, page: int, page_size: int, risk: RiskCategory | None,
                         review_status: ReviewStatus | None, search: str | None, only_orders: bool,
                         sort: str, order: str) -> tuple[RecommendationRun, list[tuple], int]:
    if run_id is None:
        run = db.scalar(select(RecommendationRun).where(RecommendationRun.status == RunStatus.COMPLETED)
                        .order_by(RecommendationRun.id.desc()).limit(1))
        if run is None:
            raise NotFoundError("No completed recommendation run yet")
    else:
        run = get_run(db, run_id)
    query = (select(ReorderRecommendation, Product.sku, Product.name)
             .join(Product, Product.id == ReorderRecommendation.product_id)
             .where(ReorderRecommendation.recommendation_run_id == run.id))
    if risk:
        query = query.where(ReorderRecommendation.risk_category == risk)
    if review_status:
        query = query.where(ReorderRecommendation.review_status == review_status)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Product.sku.ilike(pattern), Product.name.ilike(pattern)))
    if only_orders:
        query = query.where(ReorderRecommendation.suggested_qty > 0)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    if sort == "risk":
        key = case({k.value: v for k, v in RISK_ORDER.items()}, value=ReorderRecommendation.risk_category)
    else:
        key = SORTS[sort]
    key = key.desc() if order == "desc" else key.asc()
    rows = db.execute(query.order_by(key.nulls_last(), Product.sku)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return run, rows, total or 0


def review(db: Session, recommendation_id: int, status: ReviewStatus, user: User) -> tuple:
    rec = db.get(ReorderRecommendation, recommendation_id)
    if rec is None:
        raise NotFoundError(f"Recommendation {recommendation_id} not found")
    if rec.review_status == ReviewStatus.ORDERED:
        raise ConflictError("This recommendation is already on a purchase order")
    if status == ReviewStatus.ORDERED:
        raise AppError("'ordered' is set automatically when a draft purchase order is created")
    if status == ReviewStatus.APPROVED and rec.suggested_qty <= 0:
        raise AppError("Only recommendations with a suggested quantity can be approved")
    rec.review_status = status
    rec.reviewed_by, rec.reviewed_at = user.id, datetime.now(timezone.utc)
    db.commit()
    product = db.get(Product, rec.product_id)
    return rec, product.sku, product.name
