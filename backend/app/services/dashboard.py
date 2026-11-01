"""Dashboard metrics and analytics, all computed live from the database.

No figure here is hard-coded. Values that depend on simulated inputs (stock,
unit cost, order cost) are flagged in the response so the UI can label them.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.tenancy import current_shop_id
from app.models import (
    Category, DailySales, Forecast, InventoryBalance, Product, PurchaseOrder, PurchaseOrderItem, RecommendationRun, Shop,
)
from app.models.enums import PurchaseOrderStatus, RunStatus
from app.services import inventory, recommendations
from app.services.bs_calendar import fiscal_year
from app.services.forecasting import latest_completed_run

SIMULATED_FIELDS = ["inventory_value", "on_hand", "estimated_order_cost", "open_order_value"]


def _last_sales_date(db: Session) -> date | None:
    return db.scalar(select(func.max(DailySales.sales_date)))


def _sales_totals(db: Session, start: date, end: date) -> tuple[int, float]:
    units, revenue = db.execute(select(func.coalesce(func.sum(DailySales.units), 0),
                                       func.coalesce(func.sum(DailySales.units * DailySales.unit_price), 0))
                                .where(DailySales.sales_date.between(start, end))).one()
    return int(units), float(revenue)


def _pct_change(now: float, before: float) -> float | None:
    return None if before == 0 else (now - before) / before


def summary(db: Session) -> dict:
    end = _last_sales_date(db)
    stock_rows, _ = inventory.list_stock(db, page=1, page_size=100_000)
    status_counts: dict[str, int] = defaultdict(int)
    for row in stock_rows:
        status_counts[row["stock_status"]] += 1

    value, missing_cost = db.execute(
        select(func.coalesce(func.sum(InventoryBalance.on_hand * Product.unit_cost), 0),
               func.count().filter(Product.unit_cost.is_(None)))
        .join(Product, Product.id == InventoryBalance.product_id).where(Product.is_active.is_(True))).one()

    sales = None
    if end:
        units_28, revenue_28 = _sales_totals(db, end - timedelta(days=27), end)
        units_prev, revenue_prev = _sales_totals(db, end - timedelta(days=55), end - timedelta(days=28))
        fy = fiscal_year(end)
        units_fy, revenue_fy = _sales_totals(db, fy.start, end)
        sales = {"last_28_days_units": units_28, "last_28_days_revenue": round(revenue_28, 2),
                 "change_vs_previous_28_days": _pct_change(units_28, units_prev),
                 "daily_trend": sales_trend(db, days=90),
                 # Nepali fiscal year (1 Shrawan - end of Asar) up to the last sales day.
                 "fiscal_year": {"label": fy.label, "start": fy.start.isoformat(), "end": fy.end.isoformat(),
                                 "units": units_fy, "revenue": round(revenue_fy, 2)}}

    rec_run = db.scalar(select(RecommendationRun).where(RecommendationRun.status == RunStatus.COMPLETED)
                        .order_by(RecommendationRun.id.desc()).limit(1))
    rec = None
    if rec_run:
        s = recommendations.run_summary(db, rec_run.id)
        counts = s["counts"]
        rec = {"run_id": rec_run.id, "created_at": rec_run.created_at, "counts": counts,
               "products_to_reorder": counts.get("critical_stockout_risk", 0) + counts.get("reorder_soon", 0),
               "critical": counts.get("critical_stockout_risk", 0), "excess": counts.get("excess_inventory", 0),
               "estimated_order_cost": round(s["total_suggested_order_cost"], 2)}

    fc_run = latest_completed_run(db)
    forecast = None
    if fc_run:
        totals = dict(db.execute(select(Forecast.horizon, func.sum(Forecast.predicted_units))
                                 .where(Forecast.forecast_run_id == fc_run.id).group_by(Forecast.horizon)).all())
        cumulative = {f"next_{k}_days": round(float(sum(v for h, v in totals.items() if h <= k)), 1)
                      for k in (7, 14, 28) if k <= fc_run.horizon_days}
        forecast = {"run_id": fc_run.id, "model_name": fc_run.model_name, "origin_date": fc_run.origin_date,
                    "horizon_days": fc_run.horizon_days, "predicted_units": cumulative}

    open_orders = db.execute(
        select(func.count(func.distinct(PurchaseOrder.id)),
               func.coalesce(func.sum((PurchaseOrderItem.quantity_ordered - PurchaseOrderItem.quantity_received)
                                      * PurchaseOrderItem.unit_cost), 0))
        .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .where(PurchaseOrder.status.in_(inventory.OPEN_PO_STATUSES))).one()
    drafts = db.scalar(select(func.count()).select_from(PurchaseOrder)
                       .where(PurchaseOrder.status == PurchaseOrderStatus.DRAFT))
    recent, _ = inventory.list_transactions(db, page=1, page_size=10)

    return {
        "as_of": end,
        "active_products": len(stock_rows),
        "units_on_hand": sum(r["on_hand"] for r in stock_rows),
        "inventory_value": round(float(value), 2),
        "products_without_cost": int(missing_cost),
        "stock_status": dict(status_counts),
        "sales": sales,
        "recommendations": rec,
        "forecast": forecast,
        "purchase_orders": {"open": int(open_orders[0]), "open_order_value": round(float(open_orders[1]), 2),
                            "drafts": int(drafts or 0)},
        "recent_activity": recent,
        # Only the demo shop's figures are made up; a real shop's are its own records.
        "simulated_fields": SIMULATED_FIELDS if db.get(Shop, current_shop_id(db)).is_demo else [],
    }


def sales_trend(db: Session, days: int = 90, category: str | None = None, product_id: int | None = None) -> list[dict]:
    """Total units and revenue per day for the last `days` days of data."""
    end = _last_sales_date(db)
    if end is None:
        return []
    query = (select(DailySales.sales_date, func.sum(DailySales.units), func.sum(DailySales.units * DailySales.unit_price))
             .where(DailySales.sales_date > end - timedelta(days=days))
             .group_by(DailySales.sales_date).order_by(DailySales.sales_date))
    if category or product_id:
        query = query.join(Product, Product.id == DailySales.product_id)
    if category:
        query = query.join(Category, Category.id == Product.category_id).where(Category.code == category.upper())
    if product_id:
        query = query.where(DailySales.product_id == product_id)
    return [{"date": d, "units": int(u or 0), "revenue": round(float(r or 0), 2)} for d, u, r in db.execute(query)]


def weekly_trend(db: Session, weeks: int = 26, category: str | None = None) -> list[dict]:
    """Units per week (weeks start on Monday) per category, for trend charts."""
    end = _last_sales_date(db)
    if end is None:
        return []
    query = (select(DailySales.sales_date, Category.code, func.sum(DailySales.units))
             .join(Product, Product.id == DailySales.product_id).join(Category, Category.id == Product.category_id)
             .where(DailySales.sales_date > end - timedelta(weeks=weeks)).group_by(DailySales.sales_date, Category.code))
    if category:
        query = query.where(Category.code == category.upper())
    buckets: dict[tuple[date, str], int] = defaultdict(int)
    for day, code, units in db.execute(query):
        buckets[(day - timedelta(days=day.weekday()), code)] += int(units or 0)
    return [{"week_start": w, "category": c, "units": u} for (w, c), u in sorted(buckets.items())]


def category_performance(db: Session, days: int = 28) -> list[dict]:
    end = _last_sales_date(db)
    if end is None:
        return []
    start = end - timedelta(days=days - 1)
    sales = {code: (int(u or 0), float(r or 0)) for code, u, r in db.execute(
        select(Category.code, func.sum(DailySales.units), func.sum(DailySales.units * DailySales.unit_price))
        .join(Product, Product.id == DailySales.product_id).join(Category, Category.id == Product.category_id)
        .where(DailySales.sales_date.between(start, end)).group_by(Category.code))}
    stock = db.execute(
        select(Category.code, Category.name, func.count(Product.id),
               func.coalesce(func.sum(InventoryBalance.on_hand), 0),
               func.coalesce(func.sum(InventoryBalance.on_hand * Product.unit_cost), 0))
        .join(Product, Product.category_id == Category.id)
        .outerjoin(InventoryBalance, InventoryBalance.product_id == Product.id)
        .where(Product.is_active.is_(True)).group_by(Category.code, Category.name).order_by(Category.code)).all()
    out = []
    for code, name, n, on_hand, value in stock:
        units, revenue = sales.get(code, (0, 0.0))
        avg = units / days
        out.append({"category": code, "name": name, "products": n, "units_sold": units,
                    "revenue": round(revenue, 2), "avg_daily_units": round(avg, 2), "units_on_hand": int(on_hand),
                    "inventory_value": round(float(value), 2),
                    "days_of_cover": round(int(on_hand) / avg, 1) if avg > 0 else None})
    return out
