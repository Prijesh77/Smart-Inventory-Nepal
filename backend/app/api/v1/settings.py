"""Default policy and forecasting settings used by new recommendation runs, and the display currency rate."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from app.api.deps import DbSession, require_roles
from app.models import AppSetting, User
from app.models.enums import UserRole
from app.services.recommendations import policy_settings

router = APIRouter(prefix="/settings", tags=["settings"])
Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


class PolicyDefaults(BaseModel):
    service_level: float = Field(0.95, ge=0.5, lt=1, description="Target chance of no stockout per period")
    review_period_days: int = Field(7, ge=1, le=28)
    ordering_cost: float = Field(10.0, ge=0, le=10_000, description="SIMULATED cost per order")
    holding_cost_rate: float = Field(0.25, gt=0, le=1, description="SIMULATED yearly holding cost / unit cost")
    min_cycle_days: int = Field(7, ge=1, le=90)
    max_cycle_days: int = Field(28, ge=1, le=180)
    excess_cover_days: int = Field(60, ge=7, le=365)
    forecast_horizons: list[Literal[7, 14, 28]] = Field(default_factory=lambda: [7, 14, 28], min_length=1)

    @model_validator(mode="after")
    def check_cycle(self) -> PolicyDefaults:
        if self.max_cycle_days < self.min_cycle_days:
            raise ValueError("max_cycle_days must be >= min_cycle_days")
        return self


@router.get("/policy", response_model=PolicyDefaults)
def get_policy(db: DbSession) -> PolicyDefaults:
    stored = db.get(AppSetting, "policy_defaults")
    engine_values = policy_settings(db).__dict__
    horizons = (stored.value.get("forecast_horizons") if stored else None) or [7, 14, 28]
    return PolicyDefaults(**engine_values, forecast_horizons=horizons)


@router.put("/policy", response_model=PolicyDefaults, summary="Replace the default settings (admin)")
def put_policy(data: PolicyDefaults, db: DbSession, admin: Admin) -> PolicyDefaults:
    value = {**data.model_dump(), "note": "Cost values are SIMULATED assumptions"}
    setting = db.get(AppSetting, "policy_defaults")
    if setting is None:
        db.add(AppSetting(key="policy_defaults", value=value, updated_by=admin.id))
    else:
        setting.value, setting.updated_by = value, admin.id
    db.commit()
    return data


class CurrencySettings(BaseModel):
    """All amounts are stored in US dollars (the M5 data's currency); rupees are a display conversion."""

    npr_per_usd: float = Field(152.66, gt=0, le=10_000, description="Nepalese rupees per 1 US dollar")
    rate_date: date | None = Field(date(2026, 10, 29), description="Date the rate was published")
    rate_source: str = Field("Nepal Rastra Bank (selling rate)", max_length=120)


@router.get("/currency", response_model=CurrencySettings)
def get_currency(db: DbSession) -> CurrencySettings:
    stored = db.get(AppSetting, "currency")
    return CurrencySettings(**stored.value) if stored else CurrencySettings()


@router.put("/currency", response_model=CurrencySettings, summary="Set the rupee exchange rate (admin)")
def put_currency(data: CurrencySettings, db: DbSession, admin: Admin) -> CurrencySettings:
    value = data.model_dump(mode="json")
    setting = db.get(AppSetting, "currency")
    if setting is None:
        db.add(AppSetting(key="currency", value=value, updated_by=admin.id))
    else:
        setting.value, setting.updated_by = value, admin.id
    db.commit()
    return data
