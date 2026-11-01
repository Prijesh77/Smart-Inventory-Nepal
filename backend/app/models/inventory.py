"""Current stock (balances) and the audit log of every movement (transactions).

Rule enforced by the service layer: the balance is only ever changed together
with a new transaction row, inside one database transaction.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntId, string_enum
from app.models.enums import TransactionType


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("backorders >= 0", name="backorders_non_negative"),
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    on_hand: Mapped[int] = mapped_column(default=0)
    backorders: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="quantity_non_zero"),
        CheckConstraint("balance_after >= 0", name="balance_after_non_negative"),
        Index("ix_inventory_transactions_product_created", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntId, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    txn_type: Mapped[TransactionType] = mapped_column(string_enum(TransactionType, "transaction_type"))
    quantity: Mapped[int]                 # + into stock, - out of stock
    balance_after: Mapped[int]            # on-hand after this movement
    reason: Mapped[str | None] = mapped_column(String(500))
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
