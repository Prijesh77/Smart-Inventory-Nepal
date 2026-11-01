"""Calendar facts and daily demand history."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ShopOwned


class CalendarDay(Base):
    """Known-in-advance facts about each day, used as forecast features."""

    __tablename__ = "calendar_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    wm_yr_wk: Mapped[int | None]           # M5 retail week id (links weekly prices)
    event_name: Mapped[str | None] = mapped_column(String(60))
    event_type: Mapped[str | None] = mapped_column(String(30))
    snap: Mapped[bool] = mapped_column(default=False)
    is_store_open: Mapped[bool] = mapped_column(default=True)


class DailySales(ShopOwned, Base):
    __tablename__ = "daily_sales"
    __table_args__ = (CheckConstraint("units >= 0", name="units_non_negative"),)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    sales_date: Mapped[date] = mapped_column(ForeignKey("calendar_days.day"), primary_key=True, index=True)
    units: Mapped[int]
    unit_price: Mapped[Decimal | None]     # price that day, if known
    is_available: Mapped[bool] = mapped_column(default=True)   # False = not on sale / store closed
