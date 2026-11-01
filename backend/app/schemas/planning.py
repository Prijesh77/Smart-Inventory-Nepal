"""Schemas for forecasts, model evaluations and reorder recommendations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EvaluationPeriod, ReviewStatus, RiskCategory, RunStatus


class ForecastRunCreate(BaseModel):
    model_name: Literal["auto", "random_forest_v1", "moving_avg_28"] = Field(
        "auto", description="auto = the shop's own Random Forest once trained, else the 28-day moving average")
    horizon_days: Literal[7, 14, 28] = 28
    origin_date: date | None = Field(
        default=None, description="First forecast day; default = the day after the last sales data. "
                                  "An earlier date gives a back-dated forecast that can be checked against actuals.")


class ForecastRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: int
    model_name: str
    model_version: str
    origin_date: date
    horizon_days: int
    status: RunStatus
    params: dict[str, Any] | None
    metrics: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class DayValue(BaseModel):
    date: date
    units: int
    is_available: bool


class ForecastValue(BaseModel):
    date: date
    horizon: int
    predicted_units: float


class ProductForecastOut(BaseModel):
    """Actual history and forecast are separate lists so a chart can never mix them up."""
    product_id: int
    sku: str
    run: ForecastRunOut
    history: list[DayValue] = Field(description="ACTUAL sales before the forecast origin")
    actual_in_window: list[DayValue] = Field(description="ACTUAL sales inside the forecast window "
                                                         "(only for back-dated runs)")
    forecast: list[ForecastValue] = Field(description="PREDICTED units")
    total_forecast: float


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    model_name: str
    model_version: str
    period: EvaluationPeriod
    horizon_days: int
    demand_class: str
    n_observations: int
    mae: Decimal | None
    rmse: Decimal | None
    wape: Decimal | None
    bias_pct: Decimal | None


class RecommendationRunCreate(BaseModel):
    forecast_run_id: int | None = Field(default=None, description="Default: latest completed forecast run")
    service_level: float | None = Field(default=None, ge=0.5, lt=1)
    review_period_days: int | None = Field(default=None, ge=1, le=28)
    ordering_cost: float | None = Field(default=None, ge=0)
    holding_cost_rate: float | None = Field(default=None, gt=0, le=1)


class RecommendationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    forecast_run_id: int | None
    policy_settings: dict[str, Any]
    status: RunStatus
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    summary: dict[str, Any] | None = None


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    sku: str
    name: str
    on_hand: Decimal | None
    inventory_position: Decimal | None
    lead_time_days: int
    forecast_lead_time_demand: Decimal | None
    forecast_protection_demand: Decimal | None
    safety_stock: Decimal | None
    reorder_point: Decimal | None
    order_up_to: Decimal | None
    suggested_qty: int
    estimated_order_cost: Decimal | None
    stockout_probability: Decimal | None = Field(
        description="MODEL ESTIMATE of running out during the lead time (normal approximation), not an observed rate")
    days_of_cover: Decimal | None
    risk_category: RiskCategory
    explanation: str
    warnings: list[str]
    review_status: ReviewStatus
    reviewed_at: datetime | None


class RecommendationPage(BaseModel):
    run: RecommendationRunOut
    items: list[RecommendationOut]
    total: int
    page: int
    page_size: int
    pages: int


class ReviewIn(BaseModel):
    review_status: Literal[ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.PENDING]
