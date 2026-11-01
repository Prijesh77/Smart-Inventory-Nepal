"""Product master data: categories, suppliers, products."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("lead_time_days >= 1", name="lead_time_positive"),
        CheckConstraint("lead_time_sd_days >= 0", name="lead_time_sd_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    lead_time_days: Mapped[int]
    lead_time_sd_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    contact_email: Mapped[str | None] = mapped_column(String(254))


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="price_non_negative"),
        CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="cost_non_negative"),
        CheckConstraint("lead_time_days IS NULL OR lead_time_days >= 1", name="lead_time_positive"),
        CheckConstraint("min_order_qty >= 1", name="moq_positive"),
        CheckConstraint("pack_size >= 1", name="pack_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    department: Mapped[str | None] = mapped_column(String(50))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    unit_price: Mapped[Decimal]
    unit_cost: Mapped[Decimal | None]          # unknown cost is allowed; the engine warns
    lead_time_days: Mapped[int | None]         # None = use the supplier's lead time
    min_order_qty: Mapped[int] = mapped_column(default=1)
    pack_size: Mapped[int] = mapped_column(default=1)
    demand_class: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(default=True)

    category: Mapped[Category] = relationship()
    supplier: Mapped[Supplier | None] = relationship()

    @property
    def effective_lead_time_days(self) -> int | None:
        if self.lead_time_days is not None:
            return self.lead_time_days
        return self.supplier.lead_time_days if self.supplier else None
