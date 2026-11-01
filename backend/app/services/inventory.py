"""Stock levels, audited stock movements and simple low-stock alerts.

THE RULE: stock only changes through `apply_movement`, which updates the
balance and writes an inventory_transactions row in the same database
transaction. Either both are saved or neither is.

Low-stock alerts here are a transparent rule of thumb (does the stock
position cover the supplier lead time at the recent sales rate?). The full
forecast-based risk categories come from the recommendation engine.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models import (
    Category, DailySales, InventoryBalance, InventoryTransaction, Product, PurchaseOrder, PurchaseOrderItem,
    Supplier, User,
)
from app.models.enums import PurchaseOrderStatus, TransactionType

RECENT_DAYS = 28
OPEN_PO_STATUSES = (PurchaseOrderStatus.SUBMITTED, PurchaseOrderStatus.PARTIALLY_RECEIVED)
StockStatus = Literal["out_of_stock", "low", "ok", "no_recent_demand"]

# Which direction each manual movement type may go.
MANUAL_SIGNS = {
    TransactionType.ADJUSTMENT: "either",   # count corrections, damage, loss
    TransactionType.SALE: "out",
    TransactionType.RETURN: "in",
}


class StockWouldGoNegative(ConflictError):
    pass


# ---------------------------------------------------------------- movements

def apply_movement(
    db: Session, *, product_id: int, quantity: int, txn_type: TransactionType, reason: str | None,
    user: User | None, purchase_order_id: int | None = None,
) -> InventoryTransaction:
    """Change on-hand stock by `quantity` (+ in / - out) and record why.

    The balance row is locked (SELECT ... FOR UPDATE on PostgreSQL) so two
    simultaneous movements cannot both read the same old balance.
    Does not commit: the caller decides the transaction boundary.
    """
    if quantity == 0:
        raise AppError("Quantity must not be zero")
    balance = db.scalar(select(InventoryBalance).where(InventoryBalance.product_id == product_id).with_for_update())
    if balance is None:
        if db.get(Product, product_id) is None:
            raise NotFoundError(f"Product {product_id} not found")
        balance = InventoryBalance(product_id=product_id, on_hand=0, backorders=0)
        db.add(balance)
        db.flush()
    new_on_hand = balance.on_hand + quantity
    if new_on_hand < 0:
        raise StockWouldGoNegative(
            f"Only {balance.on_hand} units on hand; removing {-quantity} would make stock negative")
    balance.on_hand = new_on_hand
    txn = InventoryTransaction(product_id=product_id, txn_type=txn_type, quantity=quantity,
                               balance_after=new_on_hand, reason=reason, purchase_order_id=purchase_order_id,
                               created_by=user.id if user else None)
    db.add(txn)
    db.flush()
    return txn


def record_manual_movement(db: Session, *, product_id: int, quantity: int, txn_type: TransactionType,
                           reason: str, user: User) -> InventoryTransaction:
    """A stock change entered by a person (adjustment, sale or return), committed immediately."""
    direction = MANUAL_SIGNS.get(txn_type)
    if direction is None:
        raise AppError(f"'{txn_type.value}' movements cannot be entered manually "
                       "(receipts come from purchase orders; opening balances from setup)")
    if direction == "out" and quantity > 0 or direction == "in" and quantity < 0:
        raise AppError(f"A {txn_type.value} must {'remove' if direction == 'out' else 'add'} stock "
                       f"(quantity {'negative' if direction == 'out' else 'positive'})")
    try:
        txn = apply_movement(db, product_id=product_id, quantity=quantity, txn_type=txn_type,
                             reason=reason.strip(), user=user)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(txn)
    return txn


# ---------------------------------------------------------------- stock overview

def data_end_date(db: Session) -> date | None:
    """Last day with sales data (the app's 'today' is the day after)."""
    return db.scalar(select(func.max(DailySales.sales_date)))


def _stock_query(db: Session) -> Select:
    """One row per product with stock, on-order, recent demand rate and a status."""
    end = data_end_date(db) or date.today()
    recent = (
        select(DailySales.product_id,
               (func.sum(DailySales.units) * 1.0 / func.count()).label("avg_daily"))
        .where(DailySales.is_available.is_(True), DailySales.sales_date > end - timedelta(days=RECENT_DAYS),
               DailySales.sales_date <= end)
        .group_by(DailySales.product_id).subquery()
    )
    on_order = (
        select(PurchaseOrderItem.product_id,
               func.sum(PurchaseOrderItem.quantity_ordered - PurchaseOrderItem.quantity_received).label("qty"))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .where(PurchaseOrder.status.in_(OPEN_PO_STATUSES))
        .group_by(PurchaseOrderItem.product_id).subquery()
    )
    on_hand = func.coalesce(InventoryBalance.on_hand, 0)
    backorders = func.coalesce(InventoryBalance.backorders, 0)
    ordered = func.coalesce(on_order.c.qty, 0)
    position = on_hand + ordered - backorders
    avg_daily = func.coalesce(recent.c.avg_daily, 0.0)
    lead_time = func.coalesce(Product.lead_time_days, Supplier.lead_time_days)
    days_of_cover = case((avg_daily > 0, position / avg_daily), else_=None)
    status = case(
        (avg_daily <= 0, "no_recent_demand"),
        (on_hand <= 0, "out_of_stock"),
        (position < avg_daily * lead_time, "low"),
        else_="ok",
    )
    return (
        select(Product.id.label("product_id"), Product.sku, Product.name, Category.code.label("category_code"),
               on_hand.label("on_hand"), ordered.label("on_order"), backorders.label("backorders"),
               position.label("inventory_position"), avg_daily.label("avg_daily_sales"),
               days_of_cover.label("days_of_cover"), lead_time.label("lead_time_days"),
               status.label("stock_status"), InventoryBalance.updated_at.label("updated_at"))
        .join(Category, Category.id == Product.category_id)
        .outerjoin(Supplier, Supplier.id == Product.supplier_id)
        .outerjoin(InventoryBalance, InventoryBalance.product_id == Product.id)
        .outerjoin(recent, recent.c.product_id == Product.id)
        .outerjoin(on_order, on_order.c.product_id == Product.id)
        .where(Product.is_active.is_(True))
    )


SORTS = {"sku": "sku", "on_hand": "on_hand", "days_of_cover": "days_of_cover",
         "inventory_position": "inventory_position", "avg_daily_sales": "avg_daily_sales"}
STATUS_ORDER = {"out_of_stock": 0, "low": 1, "ok": 2, "no_recent_demand": 3}


def list_stock(db: Session, *, page: int, page_size: int, search: str | None = None, category: str | None = None,
               status: StockStatus | None = None, sort: str = "sku", order: str = "asc") -> tuple[list[dict], int]:
    base = _stock_query(db).subquery()
    query = select(base)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(base.c.sku.ilike(pattern), base.c.name.ilike(pattern)))
    if category:
        query = query.where(base.c.category_code == category.upper())
    if status:
        query = query.where(base.c.stock_status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    column = base.c[SORTS[sort]]
    ordering = column.desc() if order == "desc" else column.asc()
    rows = db.execute(query.order_by(ordering.nulls_last(), base.c.sku)
                      .offset((page - 1) * page_size).limit(page_size)).mappings().all()
    return [dict(r) for r in rows], total or 0


def stock_for_product(db: Session, product_id: int) -> dict:
    base = _stock_query(db).subquery()
    row = db.execute(select(base).where(base.c.product_id == product_id)).mappings().first()
    if row is None:
        raise NotFoundError(f"Product {product_id} not found or inactive")
    return dict(row)


def alerts(db: Session) -> list[dict]:
    """Products that are out of stock or whose position will not cover the lead time."""
    base = _stock_query(db).subquery()
    rows = db.execute(select(base).where(base.c.stock_status.in_(["out_of_stock", "low"]))).mappings().all()
    return sorted((dict(r) for r in rows),
                  key=lambda r: (STATUS_ORDER[r["stock_status"]], r["days_of_cover"] or 0, r["sku"]))


# ---------------------------------------------------------------- history

def list_transactions(db: Session, *, page: int, page_size: int, product_id: int | None = None,
                      txn_type: TransactionType | None = None, start: date | None = None,
                      end: date | None = None) -> tuple[list[dict], int]:
    query = (
        select(InventoryTransaction.id, InventoryTransaction.product_id, Product.sku, InventoryTransaction.txn_type,
               InventoryTransaction.quantity, InventoryTransaction.balance_after, InventoryTransaction.reason,
               InventoryTransaction.purchase_order_id, User.email.label("created_by_email"),
               InventoryTransaction.created_at)
        .join(Product, Product.id == InventoryTransaction.product_id)
        .outerjoin(User, User.id == InventoryTransaction.created_by)
    )
    if product_id is not None:
        query = query.where(InventoryTransaction.product_id == product_id)
    if txn_type is not None:
        query = query.where(InventoryTransaction.txn_type == txn_type)
    if start is not None:
        query = query.where(InventoryTransaction.created_at >= datetime.combine(start, datetime.min.time()))
    if end is not None:
        query = query.where(InventoryTransaction.created_at < datetime.combine(end + timedelta(days=1),
                                                                              datetime.min.time()))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).mappings().all()
    return [dict(r) for r in rows], total or 0
