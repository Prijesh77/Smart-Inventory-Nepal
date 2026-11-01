"""CSV exports.

Cells that start with = + - @ (or a tab/carriage return) are prefixed with an
apostrophe. Without this, a spreadsheet could run them as formulas when the
file is opened ("CSV injection"). Columns based on simulated inputs carry
"(simulated)" in their header.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Forecast, ForecastRun, Product
from app.services import inventory, purchasing, recommendations

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
DATASETS = ("products", "inventory", "transactions", "recommendations", "purchase-orders", "forecast")


def safe_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return str(value)                                   # numbers (even negative) are not formulas
    text = str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def to_csv(header: Sequence[str], rows: Iterable[Sequence]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return buffer.getvalue()


def products_csv(db: Session) -> str:
    products = db.scalars(select(Product).order_by(Product.sku)).all()
    return to_csv(
        ["sku", "name", "category", "department", "supplier", "unit_price", "unit_cost (simulated)",
         "lead_time_days", "min_order_qty", "pack_size", "demand_class", "is_active"],
        ([p.sku, p.name, p.category.code, p.department, p.supplier.code if p.supplier else None, p.unit_price,
          p.unit_cost, p.effective_lead_time_days, p.min_order_qty, p.pack_size, p.demand_class, p.is_active]
         for p in products))


def inventory_csv(db: Session) -> str:
    rows, _ = inventory.list_stock(db, page=1, page_size=100_000)
    cols = ["sku", "name", "category_code", "on_hand", "on_order", "backorders", "inventory_position",
            "avg_daily_sales", "days_of_cover", "lead_time_days", "stock_status"]
    header = [c + (" (simulated)" if c in {"on_hand", "on_order", "inventory_position", "days_of_cover"} else "")
              for c in cols]
    return to_csv(header, ([r[c] for c in cols] for r in rows))


def transactions_csv(db: Session) -> str:
    rows, _ = inventory.list_transactions(db, page=1, page_size=1_000_000)
    cols = ["id", "created_at", "sku", "txn_type", "quantity", "balance_after", "reason", "purchase_order_id",
            "created_by_email"]
    return to_csv(cols, ([r[c] for c in cols] for r in rows))


def recommendations_csv(db: Session, run_id: int | None) -> str:
    run, rows, _ = recommendations.list_recommendations(
        db, run_id=run_id, page=1, page_size=1_000_000, risk=None, review_status=None, search=None,
        only_orders=False, sort="risk", order="asc")
    header = ["run_id", "sku", "name", "risk_category", "on_hand (simulated)", "inventory_position (simulated)",
              "lead_time_days", "forecast_lead_time_demand", "forecast_protection_demand", "safety_stock",
              "reorder_point", "order_up_to", "suggested_qty", "estimated_order_cost (simulated)",
              "stockout_probability (model estimate)", "days_of_cover", "review_status", "explanation"]
    return to_csv(header, (
        [run.id, sku, name, r.risk_category, r.on_hand, r.inventory_position, r.lead_time_days,
         r.forecast_lead_time_demand, r.forecast_protection_demand, r.safety_stock, r.reorder_point, r.order_up_to,
         r.suggested_qty, r.estimated_order_cost, r.stockout_probability, r.days_of_cover, r.review_status,
         r.explanation] for r, sku, name in rows))


def purchase_orders_csv(db: Session) -> str:
    pos, _ = purchasing.list_orders(db, page=1, page_size=1_000_000, status=None, supplier_id=None)
    details = purchasing.line_details(db, pos)
    rows = []
    for po in pos:
        for item in po.items:
            product = details["products"][item.product_id]
            rows.append([po.po_number, details["suppliers"][po.supplier_id].code, po.status, po.expected_date,
                         product.sku, item.quantity_ordered, item.quantity_received, item.unit_cost,
                         purchasing.line_total(item.quantity_ordered, item.unit_cost)])
    return to_csv(["po_number", "supplier", "status", "expected_date", "sku", "quantity_ordered",
                   "quantity_received", "unit_cost (simulated)", "line_total (simulated)"], rows)


def forecast_csv(db: Session, run_id: int | None) -> str:
    from app.services.forecasting import latest_completed_run
    run = db.get(ForecastRun, run_id) if run_id else latest_completed_run(db)
    if run is None:
        raise NotFoundError("No forecast run to export")
    rows = db.execute(select(Product.sku, Forecast.forecast_date, Forecast.horizon, Forecast.predicted_units)
                      .join(Product, Product.id == Forecast.product_id).where(Forecast.forecast_run_id == run.id)
                      .order_by(Product.sku, Forecast.forecast_date)).all()
    return to_csv(["run_id", "model", "sku", "forecast_date", "horizon", "predicted_units"],
                  ([run.id, run.model_name, *r] for r in rows))


def export(db: Session, dataset: str, run_id: int | None) -> str:
    builders = {"products": lambda: products_csv(db), "inventory": lambda: inventory_csv(db),
                "transactions": lambda: transactions_csv(db),
                "recommendations": lambda: recommendations_csv(db, run_id),
                "purchase-orders": lambda: purchase_orders_csv(db), "forecast": lambda: forecast_csv(db, run_id)}
    return builders[dataset]()
