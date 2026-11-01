from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PurchaseOrderStatus

PO_NOTE = "Orders are only recorded in this app; nothing is sent to suppliers."


class LineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=1_000_000)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2,
                                      description="Default: the product's unit cost")


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    lines: list[LineIn] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=2000)
    expected_date: date | None = None


class PurchaseOrderUpdate(BaseModel):
    """Draft orders only. `lines`, if sent, replaces all lines."""
    notes: str | None = Field(default=None, max_length=2000)
    expected_date: date | None = None
    lines: list[LineIn] | None = Field(default=None, min_length=1)


class FromRecommendationsIn(BaseModel):
    recommendation_ids: list[int] | None = Field(
        default=None, description="Default: all approved recommendations of the latest completed run")


class ReceiveLine(BaseModel):
    item_id: int
    quantity: int = Field(gt=0)


class ReceiveIn(BaseModel):
    lines: list[ReceiveLine] = Field(min_length=1)


class LineOut(BaseModel):
    id: int
    product_id: int
    sku: str
    name: str
    quantity_ordered: int
    quantity_received: int
    quantity_outstanding: int
    unit_cost: Decimal | None
    line_total: Decimal | None
    recommendation_id: int | None


class PurchaseOrderOut(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    status: PurchaseOrderStatus
    expected_date: date | None
    submitted_at: datetime | None
    received_at: datetime | None
    notes: str | None
    created_at: datetime
    lines: list[LineOut]
    total_units: int
    total_cost: Decimal
    note: str = PO_NOTE


class PurchaseOrderPage(BaseModel):
    items: list[PurchaseOrderOut]
    total: int
    page: int
    page_size: int
    pages: int
