from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import TransactionType


class StockItem(BaseModel):
    product_id: int
    sku: str
    name: str
    category_code: str
    on_hand: int
    on_order: int = Field(description="Ordered but not yet received, from submitted purchase orders")
    backorders: int
    inventory_position: int = Field(description="on_hand + on_order - backorders")
    avg_daily_sales: float = Field(description="Average units per available day over the last 28 days of data")
    days_of_cover: float | None = Field(description="inventory_position / avg_daily_sales (None if no recent sales)")
    lead_time_days: int | None
    stock_status: Literal["out_of_stock", "low", "ok", "no_recent_demand"] = Field(
        description="low = position will not cover the supplier lead time at the recent sales rate")
    updated_at: datetime | None


class AdjustmentIn(BaseModel):
    product_id: int
    quantity: int = Field(description="Positive adds stock, negative removes it; cannot be 0")
    txn_type: Literal[TransactionType.ADJUSTMENT, TransactionType.SALE, TransactionType.RETURN] = (
        TransactionType.ADJUSTMENT)
    reason: str = Field(min_length=3, max_length=500, description="Why the stock changed (required for audit)")


class TransactionOut(BaseModel):
    id: int
    product_id: int
    sku: str
    txn_type: TransactionType
    quantity: int
    balance_after: int
    reason: str | None
    purchase_order_id: int | None
    created_by_email: str | None
    created_at: datetime
