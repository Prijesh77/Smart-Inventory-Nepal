"""Forecast runs, their predictions, and stored model evaluation scores."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Quantity, string_enum
from app.models.enums import EvaluationPeriod, RunStatus


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (CheckConstraint("horizon_days BETWEEN 1 AND 90", name="horizon_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(60))       # e.g. random_forest_v1, moving_avg_28
    model_version: Mapped[str] = mapped_column(String(60))
    origin_date: Mapped[date] = mapped_column(Date)           # first forecast day; history ends the day before
    horizon_days: Mapped[int]
    status: Mapped[RunStatus] = mapped_column(string_enum(RunStatus, "forecast_run_status"),
                                              default=RunStatus.PENDING)
    params: Mapped[dict[str, Any] | None]
    metrics: Mapped[dict[str, Any] | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        CheckConstraint("predicted_units >= 0", name="prediction_non_negative"),
        CheckConstraint("horizon >= 1", name="horizon_positive"),
        Index("ix_forecasts_product_date", "product_id", "forecast_date"),
    )

    forecast_run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"),
                                                 primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    forecast_date: Mapped[date] = mapped_column(Date, primary_key=True)
    horizon: Mapped[int]                      # 1 = first forecast day
    predicted_units: Mapped[Decimal] = mapped_column(Quantity)


class ModelEvaluation(Base):
    """Backtest scores (from Phase 3) shown on the Forecasting page."""

    __tablename__ = "model_evaluations"
    __table_args__ = (
        UniqueConstraint("model_name", "model_version", "period", "horizon_days", "demand_class",
                         name="uq_model_evaluations_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(60))
    model_version: Mapped[str] = mapped_column(String(60))
    period: Mapped[EvaluationPeriod] = mapped_column(string_enum(EvaluationPeriod, "evaluation_period"))
    horizon_days: Mapped[int]
    demand_class: Mapped[str] = mapped_column(String(30))      # "all" or a class name
    n_observations: Mapped[int]
    mae: Mapped[Decimal | None] = mapped_column(Quantity)
    rmse: Mapped[Decimal | None] = mapped_column(Quantity)
    wape: Mapped[Decimal | None] = mapped_column(Quantity)
    bias_pct: Mapped[Decimal | None] = mapped_column(Quantity)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
