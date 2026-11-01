from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_roles
from app.models import User
from app.models.enums import TransactionType, UserRole
from app.schemas.common import Page
from app.schemas.inventory import AdjustmentIn, StockItem, TransactionOut
from app.services import inventory as service

router = APIRouter(prefix="/inventory", tags=["inventory"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


@router.get("", response_model=Page[StockItem], summary="Current stock for all active products")
def list_stock(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=100),
    category: str | None = None,
    status_filter: service.StockStatus | None = Query(None, alias="status"),
    sort: Literal["sku", "on_hand", "days_of_cover", "inventory_position", "avg_daily_sales"] = "sku",
    order: Literal["asc", "desc"] = "asc",
) -> Page[StockItem]:
    items, total = service.list_stock(db, page=page, page_size=page_size, search=search, category=category,
                                      status=status_filter, sort=sort, order=order)
    return Page.build([StockItem(**i) for i in items], total, page, page_size)


@router.get("/alerts", response_model=list[StockItem],
            summary="Out-of-stock and low-stock products, most urgent first")
def low_stock_alerts(db: DbSession) -> list[StockItem]:
    return [StockItem(**i) for i in service.alerts(db)]


@router.get("/transactions", response_model=Page[TransactionOut], summary="Audit log of stock movements, newest first")
def list_transactions(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    product_id: int | None = None,
    txn_type: TransactionType | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Page[TransactionOut]:
    items, total = service.list_transactions(db, page=page, page_size=page_size, product_id=product_id,
                                             txn_type=txn_type, start=start, end=end)
    return Page.build([TransactionOut(**i) for i in items], total, page, page_size)


@router.get("/{product_id}", response_model=StockItem, summary="Current stock for one product")
def product_stock(product_id: int, db: DbSession) -> StockItem:
    return StockItem(**service.stock_for_product(db, product_id))


@router.post("/adjustments", response_model=TransactionOut, status_code=status.HTTP_201_CREATED,
             summary="Record a stock adjustment, sale or return (manager or admin)")
def create_adjustment(data: AdjustmentIn, db: DbSession, user: Manager) -> TransactionOut:
    txn = service.record_manual_movement(db, product_id=data.product_id, quantity=data.quantity,
                                         txn_type=data.txn_type, reason=data.reason, user=user)
    items, _ = service.list_transactions(db, page=1, page_size=1, product_id=txn.product_id)
    return TransactionOut(**items[0])
