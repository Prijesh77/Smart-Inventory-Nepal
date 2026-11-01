"""Simulation runs, CSV import jobs and application settings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ShopOwned, string_enum
from app.models.enums import RunStatus


class SimulationRun(ShopOwned, Base):
    """Inventory simulations started from the app. Results are SIMULATED by definition."""

    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[RunStatus] = mapped_column(string_enum(RunStatus, "simulation_run_status"),
                                              default=RunStatus.PENDING)
    params: Mapped[dict[str, Any]]
    results: Mapped[dict[str, Any] | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportJob(ShopOwned, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint("rows_valid + rows_invalid <= rows_total", name="row_counts_consistent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    import_type: Mapped[str] = mapped_column(String(30))       # e.g. "sales", "products"
    status: Mapped[RunStatus] = mapped_column(string_enum(RunStatus, "import_status"), default=RunStatus.PENDING)
    rows_total: Mapped[int] = mapped_column(default=0)
    rows_valid: Mapped[int] = mapped_column(default=0)
    rows_invalid: Mapped[int] = mapped_column(default=0)
    errors: Mapped[dict[str, Any] | None]                    # row-level validation errors
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(ShopOwned, Base):
    """Key-value settings such as default service level, horizons and cost assumptions."""

    __tablename__ = "app_settings"

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]]
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
