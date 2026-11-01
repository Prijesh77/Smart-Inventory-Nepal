"""Reorder recommendation runs: apply the tested engine (ml/inventory/recommend.py)
to every active product using a stored forecast run and current stock.

Safety stock uses the forecast model's MEASURED past errors (Phase 4 finding):
  1. Backtest the same model at up to 16 weekly origins whose whole protection
     period ended before the forecast origin (and that had enough history for the model).
  2. >= 8 complete periods for the item: RMSE of its protection-period errors.
  3. Otherwise >= 14 daily errors: daily RMSE with the sqrt(days) rule.
  4. Otherwise, a shop with little history (but >= 14 days of the item's sales): the
     textbook rule, the standard deviation of daily sales with the sqrt(days) rule.
     Clearly labelled as an estimate, and replaced by measured errors once there is
     enough history (about 5 weeks with the moving average).
  5. Otherwise: "insufficient data" (no recommendation is invented).

Festival ahead: when a festival's build-up starts within 3 weeks, last year's
same festival is looked up in the item's own sales. If the item sold clearly more
then (>= 1.3x its normal amount), the recommendation says so, and compares the
forecast for the festival days with what last time's pattern implies: if the forecast
falls short (always with the moving average, often with a forest that has seen only
one such festival), it estimates the extra units.
The suggested quantity itself is not changed: the shop decides.
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
from app.db.tenancy import current_shop_id, shop_session
from app.models import AppSetting, Forecast, ForecastRun, Product, RecommendationRun, ReorderRecommendation, User
from app.models.enums import ReviewStatus, RiskCategory, RunStatus
from app.services import inventory
from app.services.forecast_engine import ForecastContext, forecast_matrix, load_context, min_history_days
from app.services.forecasting import latest_completed_run
from app.services.bs_calendar import to_bs
from ml.calendar.festivals import previous, upcoming
from ml.inventory import formulas as f
from ml.inventory.recommend import ItemState, PolicySettings, insufficient, recommend

logger = logging.getLogger("app.recommendations")
ERROR_ORIGINS = 16
FESTIVAL_LOOKAHEAD_DAYS = 21          # warn when a festival build-up starts within 3 weeks
FESTIVAL_MIN_UPLIFT = 1.3             # ... and the item sold at least 30% more around it last time
FESTIVAL_BASELINE_DAYS = 28           # "normal" = the 4 weeks before last year's build-up
MIN_SALES_DAYS_FOR_ESTIMATE = 14     # fallback 4: days of the item's own sales needed
SALES_SIGMA_WINDOW = 56              # fallback 4 uses at most the last 8 weeks
POLICY_FIELDS = {fld.name for fld in fields(PolicySettings)}
RISK_ORDER = {RiskCategory.CRITICAL: 0, RiskCategory.REORDER_SOON: 1, RiskCategory.EXCESS: 2,
              RiskCategory.INSUFFICIENT: 3, RiskCategory.HEALTHY: 4}


# ---------------------------------------------------------------- policy

def policy_settings(db: Session, overrides: dict[str, Any] | None = None) -> PolicySettings:
    """Stored defaults (app_settings.policy_defaults), then any per-run overrides."""
    stored = db.get(AppSetting, (current_shop_id(db), "policy_defaults"))
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
    starts = [s for s in starts if s - 1 >= min_history_days(model_name)]
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


def festival_note(ctx: ForecastContext, i: int, origin, forecast: np.ndarray, protection_days: int,
                  model_name: str) -> str | None:
    """'Festival ahead' advice for item row i, from its own sales around last year's same festival."""
    best = None
    for fest in upcoming(origin, FESTIVAL_LOOKAHEAD_DAYS):
        last = previous(fest)
        if last is None:
            continue
        start, end = (ctx.d_num(d) for d in last.window)
        if start - FESTIVAL_BASELINE_DAYS < 1 or end >= ctx.d_num(origin):
            continue                                           # last year's festival is not in this shop's history
        sales = ctx.panel.sales[i]
        window, normal = sales[start - 1: end], sales[start - 1 - FESTIVAL_BASELINE_DAYS: start - 1]
        if np.isnan(window).sum() > len(window) / 2 or np.isnan(normal).all():
            continue
        base = float(np.nanmean(normal))
        uplift = float(np.nanmean(window)) / base if base > 0 else None
        if uplift is None or uplift < FESTIVAL_MIN_UPLIFT or (best and uplift <= best[1]):
            continue
        best = (fest, uplift, last)
    if best is None:
        return None
    fest, uplift, last = best
    days = (fest.main - origin).days
    when = f"in {days} days" if days > 0 else "now"
    text = (f"Festival ahead: {fest.name} ({fest.main_label} on {to_bs(fest.main).label}, {when}). Around "
            f"{last.name} last time, this item sold {uplift:.1f}x its normal amount.")
    # Compare what the forecast expects on the festival days inside the protection period with what last
    # time's pattern implies. Works for any model: a forest that learned the rise shows little or no gap.
    first, last_day = (ctx.d_num(d) - ctx.d_num(origin) for d in fest.window)
    lo, hi = max(first, 0), min(last_day + 1, protection_days)
    if hi <= lo:
        return text + " It falls after this order would arrive, so plan for it in the next order."
    o = ctx.d_num(min(origin, fest.window[0]))
    normal_now = float(np.nanmean(ctx.panel.sales[i, max(o - 1 - FESTIVAL_BASELINE_DAYS, 0): o - 1]))
    forecast_days = float(forecast[lo:hi].sum())
    implied = normal_now * uplift * (hi - lo)
    if np.isnan(implied) or implied - forecast_days < 1:
        return text + " The forecast already expects this rise."
    why = " (the moving average does not know festivals)" if model_name == "moving_avg_28" else ""
    return text + (f" The forecast{why} expects about {forecast_days:.0f} units on those days; last time's pattern "
                   f"suggests about {implied:.0f}. Consider about {round(implied - forecast_days)} more units than "
                   f"suggested.")


def sales_sigmas(ctx: ForecastContext, origin) -> list[tuple[float, int] | None]:
    """Fallback 4, per item: (std of daily sales, days used) over the last 8 weeks before the origin."""
    history = ctx.panel.sales[:, max(ctx.d_num(origin) - 1 - SALES_SIGMA_WINDOW, 0): ctx.d_num(origin) - 1]
    out: list[tuple[float, int] | None] = []
    for row in history:
        known = row[~np.isnan(row)]
        out.append((float(np.std(known)), int(known.size)) if known.size >= MIN_SALES_DAYS_FOR_ESTIMATE else None)
    return out


def execute_run(session_factory: sessionmaker[Session], shop_id: int, run_id: int) -> None:
    with shop_session(session_factory, shop_id) as db:
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
    fallback_sigma = sales_sigmas(ctx, forecast_run.origin_date)

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
            sigma, method = daily_sigma[i], None
            if period_sigma[i] is not None:
                method = "measured protection-period forecast errors"
            elif sigma is not None:
                method = "daily forecast errors x sqrt(days)"
            elif fallback_sigma[i] is not None:
                sigma, days = fallback_sigma[i]
                method = (f"an ESTIMATE: day-to-day variation of the last {days} days of sales (little history "
                          f"yet; measured forecast errors replace it after about 5 weeks of sales)")
            rec = recommend(state, forecasts[product.id], sigma, policy, period_sigma=period_sigma[i])
        note = (festival_note(ctx, i, forecast_run.origin_date, forecasts[product.id],
                              lead_time + policy.review_period_days, forecast_run.model_name)
                if i is not None and product.id in forecasts and lead_time is not None else None)
        records.append(_to_row(run.id, product.id, rec, method, note))
    db.add_all(records)
    db.flush()
    return len(records)


def _num(value: float | None, places: int = 3) -> Decimal | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return Decimal(str(round(float(value), places)))


def _to_row(run_id: int, product_id: int, rec, sigma_method: str | None,
            festival: str | None = None) -> ReorderRecommendation:
    warnings = ([festival] if festival else []) + list(rec.warnings)       # festival first: most useful
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
