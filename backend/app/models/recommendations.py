"""Reorder recommendation runs and their per-product results (engine output)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Quantity, string_enum
from app.models.enums import ReviewStatus, RiskCategory, RunStatus


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    forecast_run_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_runs.id"))
    policy_settings: Mapped[dict[str, Any]]           # service level, review period, costs used
    status: Mapped[RunStatus] = mapped_column(string_enum(RunStatus, "recommendation_run_status"),
                                              default=RunStatus.PENDING)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReorderRecommendation(Base):
    __tablename__ = "reorder_recommendations"
    __table_args__ = (
        UniqueConstraint("recommendation_run_id", "product_id", name="uq_reorder_recommendations_run_product"),
        CheckConstraint("suggested_qty >= 0", name="qty_non_negative"),
        CheckConstraint("stockout_probability IS NULL OR (stockout_probability >= 0 AND stockout_probability <= 1)",
                        name="probability_range"),
        Index("ix_reorder_recommendations_risk", "risk_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_run_id: Mapped[int] = mapped_column(ForeignKey("recommendation_runs.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    on_hand: Mapped[Decimal] = mapped_column(Quantity)
    inventory_position: Mapped[Decimal] = mapped_column(Quantity)
    lead_time_days: Mapped[int]
    forecast_lead_time_demand: Mapped[Decimal | None] = mapped_column(Quantity)
    forecast_protection_demand: Mapped[Decimal | None] = mapped_column(Quantity)
    safety_stock: Mapped[Decimal | None] = mapped_column(Quantity)
    reorder_point: Mapped[Decimal | None] = mapped_column(Quantity)
    order_up_to: Mapped[Decimal | None] = mapped_column(Quantity)
    suggested_qty: Mapped[int]
    estimated_order_cost: Mapped[Decimal | None]
    stockout_probability: Mapped[Decimal | None] = mapped_column(Quantity)   # model estimate, not observed
    days_of_cover: Mapped[Decimal | None] = mapped_column(Quantity)
    risk_category: Mapped[RiskCategory] = mapped_column(string_enum(RiskCategory, "risk_category"))
    explanation: Mapped[str] = mapped_column(Text)
    warnings: Mapped[dict[str, Any] | None]   # {"messages": [...]}
    review_status: Mapped[ReviewStatus] = mapped_column(string_enum(ReviewStatus, "review_status"),
                                                        default=ReviewStatus.PENDING)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
