from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

SkuStr = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_\-]+$",
                              description="Letters, digits, '_' or '-'. Stored in upper case.")]
MoneyIn = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    lead_time_days: int
    lead_time_sd_days: Decimal
    contact_email: str | None = None


class ProductCreate(BaseModel):
    sku: SkuStr
    name: str = Field(min_length=1, max_length=200)
    category_code: str = Field(min_length=1, max_length=30)
    department: str | None = Field(default=None, max_length=50)
    supplier_id: int | None = None
    unit_price: MoneyIn
    unit_cost: MoneyIn | None = None
    lead_time_days: int | None = Field(default=None, ge=1, le=365,
                                       description="Leave empty to use the supplier's lead time")
    min_order_qty: int = Field(default=1, ge=1)
    pack_size: int = Field(default=1, ge=1)

    @field_validator("sku", mode="before")   # before: trim/upper-case, then check the pattern
    @classmethod
    def normalise_sku(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name cannot be blank")
        return value.strip()


class ProductUpdate(BaseModel):
    """All fields optional; only the ones sent are changed. The SKU cannot change (audit history uses it)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_code: str | None = Field(default=None, min_length=1, max_length=30)
    department: str | None = Field(default=None, max_length=50)
    supplier_id: int | None = None
    unit_price: MoneyIn | None = None
    unit_cost: MoneyIn | None = None
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    min_order_qty: int | None = Field(default=None, ge=1)
    pack_size: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    category: CategoryOut
    department: str | None
    supplier: SupplierOut | None
    unit_price: Decimal
    unit_cost: Decimal | None
    lead_time_days: int | None
    effective_lead_time_days: int | None
    min_order_qty: int
    pack_size: int
    demand_class: str | None
    is_active: bool
    on_hand: int
    created_at: datetime
    updated_at: datetime


class SalesPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sales_date: date
    units: int
    unit_price: Decimal | None
    is_available: bool


class SalesHistory(BaseModel):
    product_id: int
    sku: str
    start: date
    end: date
    total_units: int
    points: list[SalesPoint]
