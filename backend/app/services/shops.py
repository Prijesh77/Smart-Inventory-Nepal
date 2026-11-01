"""Creating shops (tenants). Shops are set up by an operator script for now (backend/scripts/create_shop.py)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.tenancy import all_shops, use_shop
from app.models import AppSetting, Shop

DEFAULT_POLICY = {"service_level": 0.95, "review_period_days": 7, "ordering_cost": 200.0,
                  "holding_cost_rate": 0.25, "min_cycle_days": 7, "max_cycle_days": 28,
                  "excess_cover_days": 60, "forecast_horizons": [7, 14, 28],
                  "note": "Cost values are assumptions; amounts in NPR"}


def create_shop(session: Session, name: str, *, is_demo: bool = False) -> Shop:
    """Add a shop with the default reorder settings, and switch the session to it (caller commits)."""
    name = name.strip()
    if not name:
        raise AppError("A shop needs a name")
    shop = Shop(name=name, is_demo=is_demo)
    session.add(shop)
    session.flush()
    use_shop(session, shop.id)
    session.add(AppSetting(key="policy_defaults", value=DEFAULT_POLICY))
    session.flush()
    return shop


def list_shops(session: Session) -> list[Shop]:
    with all_shops(session):
        return list(session.scalars(select(Shop).order_by(Shop.id)))
