from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SaleLineIn(BaseModel):
    product_id: int
    units: int = Field(ge=-100_000, le=100_000,
                       description="Units sold (positive). A negative number corrects an earlier entry for that day.")


class SalesEntryIn(BaseModel):
    sales_date: date
    items: list[SaleLineIn] = Field(default_factory=list, max_length=500)
    close_day: bool = Field(default=False,
                            description="Also record 0 units for every active product with no sales that day")


class SaleLineOut(BaseModel):
    product_id: int
    sku: str
    name: str
    units: int
    unit_price: Decimal
    amount: Decimal
    on_hand: int = Field(description="Stock on hand now, after the sales")


class SalesDayOut(BaseModel):
    sales_date: date
    items: list[SaleLineOut] = Field(description="Products with units sold that day")
    total_units: int
    total_amount: Decimal
    products_recorded: int = Field(description="Products with a sales row that day, including 0-unit rows")
    active_products: int
    zero_rows_added: int | None = Field(default=None, description="Set when a day was closed")


class PartialDayOut(BaseModel):
    date: date
    products_recorded: int
    products_expected: int = Field(description="Active products that had started selling by that day")


class SalesCoverageOut(BaseModel):
    window_start: date | None = Field(description="First day of the 28 days checked (ending on the last sales day)")
    window_end: date | None
    recorded_days: int = Field(description="Days in the window with any sales recorded")
    missing_days: list[date] = Field(description="Open days in the window with nothing recorded; forecasts skip them")
    partial_days: list[PartialDayOut] = Field(
        description="Recent days where only some products were entered and the day was not closed")
