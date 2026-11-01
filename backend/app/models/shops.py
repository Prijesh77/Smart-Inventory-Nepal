"""Shops (tenants). Each business has its own private products, stock, sales, orders, forecasts and users."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    is_demo: Mapped[bool] = mapped_column(default=False)    # True = synthetic demo data, labelled in the app
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
