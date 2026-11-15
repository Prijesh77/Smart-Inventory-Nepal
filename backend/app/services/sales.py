"""Sales entered by hand at the counter, one day at a time.

Each entry does two things in one database transaction: it adds to that day's
units in daily_sales (what the forecasts learn from) and takes the units out of
stock through `inventory.apply_movement` (so on-hand stays true). A negative
entry corrects a mistake: it lowers the day's total and puts the units back.

Excel import (services/imports.py) is still the way to load past history; it
replaces a day's units and does not touch stock.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models import CalendarDay, DailySales, InventoryBalance, Product, User
from app.models.enums import TransactionType
from app.services.inventory import apply_movement

MAX_DAYS_BACK = 60      # older history belongs in an Excel import, and a typo in the year should not move stock


def _check_day(day: date) -> None:
    today = date.today()
    if day > today:
        raise AppError("Sales cannot be recorded for a future date")
    if day < today - timedelta(days=MAX_DAYS_BACK):
        raise AppError(f"Sales older than {MAX_DAYS_BACK} days are loaded with the Excel import in Settings")


def _ensure_calendar_day(db: Session, day: date) -> bool:
    """Make sure the day exists in the calendar; returns whether the store was open."""
    row = db.get(CalendarDay, day)
    if row is None:
        row = CalendarDay(day=day, is_store_open=True)
        db.add(row)
        db.flush()
    return row.is_store_open


def record_sales(db: Session, *, day: date, items: list[tuple[int, int]], close_day: bool, user: User) -> dict:
    """Add `items` (product_id, units) to the day's sales and move stock. All of it is saved, or none.

    `close_day` also records 0 units for every active product with no sales row that day, so the
    forecasts see a quiet day as "sold nothing" instead of "no data".
    """
    _check_day(day)
    units_by_product: dict[int, int] = {}
    for product_id, units in items:                       # the same product twice in one entry is added up
        units_by_product[product_id] = units_by_product.get(product_id, 0) + units
    units_by_product = {p: u for p, u in units_by_product.items() if u != 0}
    if not units_by_product and not close_day:
        raise AppError("Enter at least one product with units sold")
    try:
        is_open = _ensure_calendar_day(db, day)
        products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(units_by_product)))}
        for product_id, units in sorted(units_by_product.items()):
            product = products.get(product_id)
            if product is None:
                raise NotFoundError(f"Product {product_id} not found")
            if not product.is_active:
                raise AppError(f"{product.sku} is inactive; activate it before recording sales")
            row = db.get(DailySales, (product_id, day))
            total = (row.units if row else 0) + units
            if total < 0:
                raise AppError(f"{product.sku}: only {row.units if row else 0} units are recorded for {day}; "
                               f"a correction cannot remove {-units}")
            apply_movement(db, product_id=product_id, quantity=-units, user=user,
                           txn_type=TransactionType.SALE if units > 0 else TransactionType.ADJUSTMENT,
                           reason=f"Sales entry for {day}" if units > 0 else f"Sales correction for {day}")
            if row is None:
                db.add(DailySales(product_id=product_id, sales_date=day, units=total, unit_price=product.unit_price,
                                  is_available=is_open))
            else:
                row.units = total
                if row.unit_price is None:
                    row.unit_price = product.unit_price
        zero_rows = _fill_zero_rows(db, day, is_open) if close_day else 0
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {**day_summary(db, day), "zero_rows_added": zero_rows}


def _fill_zero_rows(db: Session, day: date, is_open: bool) -> int:
    db.flush()
    have = set(db.scalars(select(DailySales.product_id).where(DailySales.sales_date == day)))
    missing = [p for p in db.scalars(select(Product).where(Product.is_active.is_(True))) if p.id not in have]
    db.add_all([DailySales(product_id=p.id, sales_date=day, units=0, unit_price=p.unit_price, is_available=is_open)
                for p in missing])
    return len(missing)


def day_summary(db: Session, day: date) -> dict:
    """What has been recorded for one day: each product with sales, plus totals."""
    rows = db.execute(
        select(Product.id.label("product_id"), Product.sku, Product.name, DailySales.units,
               func.coalesce(DailySales.unit_price, Product.unit_price).label("unit_price"),
               func.coalesce(InventoryBalance.on_hand, 0).label("on_hand"))
        .join(Product, Product.id == DailySales.product_id)
        .outerjoin(InventoryBalance, InventoryBalance.product_id == Product.id)
        .where(DailySales.sales_date == day, DailySales.units > 0)
        .order_by(Product.sku)
    ).mappings().all()
    items = [{**r, "amount": Decimal(r["units"]) * Decimal(r["unit_price"])} for r in rows]
    recorded = db.scalar(select(func.count()).select_from(DailySales).where(DailySales.sales_date == day)) or 0
    active = db.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True))) or 0
    return {
        "sales_date": day,
        "items": items,
        "total_units": sum(i["units"] for i in items),
        "total_amount": sum((i["amount"] for i in items), Decimal("0")),
        "products_recorded": recorded,          # products with a row that day, including 0-unit rows
        "active_products": active,
    }
