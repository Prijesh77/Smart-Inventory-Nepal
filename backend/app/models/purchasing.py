"""Purchase orders. The app only creates and tracks them; it never sends orders to suppliers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ShopOwned, TimestampMixin, string_enum
from app.models.enums import PurchaseOrderStatus


class PurchaseOrder(ShopOwned, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("shop_id", "po_number", name="uq_purchase_orders_shop_po_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30))     # PO-000001, numbered per shop
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        string_enum(PurchaseOrderStatus, "po_status"), default=PurchaseOrderStatus.DRAFT, index=True
    )
    expected_date: Mapped[date | None] = mapped_column(Date)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    items: Mapped[list[PurchaseOrderItem]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )


class PurchaseOrderItem(ShopOwned, Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("quantity_ordered > 0", name="ordered_positive"),
        CheckConstraint("quantity_received >= 0 AND quantity_received <= quantity_ordered",
                        name="received_within_ordered"),
        CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="cost_non_negative"),
        UniqueConstraint("purchase_order_id", "product_id", name="uq_purchase_order_items_po_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity_ordered: Mapped[int]
    quantity_received: Mapped[int] = mapped_column(default=0)
    unit_cost: Mapped[Decimal | None]
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("reorder_recommendations.id"))

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")
