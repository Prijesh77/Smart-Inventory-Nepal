"""Turn a forecast and an item's stock situation into an explained reorder recommendation.

Deterministic parts (reorder point, order quantity, risk category) follow
fixed rules from the inputs. The stockout probability is a separate model
estimate and is labelled as such. No confidence score is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ml.inventory import formulas as f

CRITICAL = "critical_stockout_risk"
REORDER_SOON = "reorder_soon"
HEALTHY = "healthy"
EXCESS = "excess_inventory"
INSUFFICIENT = "insufficient_data"
SLOW_CLASSES = {"intermittent", "lumpy"}


@dataclass(frozen=True)
class PolicySettings:
    """Configurable policy assumptions. All costs are SIMULATED inputs, not retailer data."""

    service_level: float = 0.95        # target chance of no stockout per protection period
    review_period_days: int = 7        # how often each item is checked
    ordering_cost: float = 200.0       # fixed cost per order line (NPR)
    holding_cost_rate: float = 0.25    # yearly holding cost as a share of unit cost
    min_cycle_days: int = 7            # order at least ~one review period of demand ...
    max_cycle_days: int = 28           # ... and at most ~four weeks, whatever EOQ says
    excess_cover_days: int = 60        # stock lasting longer than this is "excess"


@dataclass(frozen=True)
class ItemState:
    sku: str
    name: str
    on_hand: float
    on_order: float
    lead_time_days: int
    backorders: float = 0.0
    unit_cost: float | None = None
    min_order_qty: int = 1
    pack_size: int = 1
    sigma_lead_time_days: float = 0.0
    demand_class: str | None = None


@dataclass(frozen=True)
class Recommendation:
    sku: str
    name: str
    on_hand: float
    inventory_position: float
    lead_time_days: int
    protection_days: int
    forecast_lead_time_demand: float
    forecast_protection_demand: float
    safety_stock: float
    reorder_point: float
    order_up_to: float
    suggested_qty: int
    estimated_order_cost: float | None
    stockout_probability: float | None   # model estimate over the lead time, see formulas.py
    days_of_cover: float | None
    risk_category: str
    explanation: str
    warnings: list[str] = field(default_factory=list)


def cycle_quantity(mean_daily: float, item: ItemState, policy: PolicySettings) -> float:
    """Planned order size: EOQ when costs are known, kept between min and max cycle days."""
    low, high = mean_daily * policy.min_cycle_days, mean_daily * policy.max_cycle_days
    if item.unit_cost is None or item.unit_cost <= 0:
        return low
    eoq = f.economic_order_quantity(
        annual_demand=mean_daily * 365,
        ordering_cost=policy.ordering_cost,
        holding_cost_per_unit_year=policy.holding_cost_rate * item.unit_cost,
    )
    return min(max(eoq, low), high)


def classify_risk(position: float, lead_time_demand: float, reorder_pt: float, order_up_to: float,
                  days_of_cover: float | None, policy: PolicySettings) -> str:
    """Transparent business rules, checked in this order:

    1. critical: position < expected demand during the lead time
       (even an order placed today is expected to arrive after stock runs out)
    2. reorder soon: position <= reorder point
    3. excess: position > order-up-to level AND cover > excess_cover_days
       (or stock with no forecast demand at all)
    4. healthy: everything else
    """
    if position < lead_time_demand:
        return CRITICAL
    if position <= reorder_pt:
        return REORDER_SOON
    if position > order_up_to and (days_of_cover is None or days_of_cover > policy.excess_cover_days):
        return EXCESS
    return HEALTHY


def _explain(rec: dict, item: ItemState, policy: PolicySettings) -> str:
    ip, s = rec["inventory_position"], rec["reorder_point"]
    base = (
        f"Inventory position is {ip:.0f} units (on hand {item.on_hand:.0f} + on order {item.on_order:.0f}"
        f" - backorders {item.backorders:.0f}). Forecast demand over the {item.lead_time_days}-day lead time"
        f" is {rec['forecast_lead_time_demand']:.1f}, and over the {rec['protection_days']}-day protection"
        f" period (lead time + {policy.review_period_days}-day review) {rec['forecast_protection_demand']:.1f}."
        f" With {rec['safety_stock']:.1f} units of safety stock for a {policy.service_level:.0%} service"
        f" target, the reorder point is {s:.1f}."
    )
    category = rec["risk_category"]
    if category == CRITICAL:
        action = (f" Position is below expected lead-time demand, so a stockout is likely before new stock"
                  f" arrives. Order {rec['suggested_qty']} units now and consider expediting.")
    elif category == REORDER_SOON:
        action = (f" Position is at or below the reorder point. Order {rec['suggested_qty']} units to reach"
                  f" the order-up-to level of {rec['order_up_to']:.1f}.")
    elif category == EXCESS:
        cover = rec["days_of_cover"]
        cover_text = "no forecast demand" if cover is None else f"about {cover:.0f} days of cover"
        action = f" No order needed. Stock is above the order-up-to level with {cover_text}; review for excess."
    else:
        action = " Position is above the reorder point. No order needed this review."
    return base + action


def insufficient(item: ItemState, reason: str) -> Recommendation:
    """Recommendation shell when there is not enough information to calculate."""
    position = f.inventory_position(item.on_hand, item.on_order, item.backorders)
    nan = float("nan")
    return Recommendation(
        sku=item.sku, name=item.name, on_hand=item.on_hand, inventory_position=position,
        lead_time_days=item.lead_time_days,
        protection_days=item.lead_time_days, forecast_lead_time_demand=nan, forecast_protection_demand=nan,
        safety_stock=nan, reorder_point=nan, order_up_to=nan, suggested_qty=0, estimated_order_cost=None,
        stockout_probability=None, days_of_cover=None, risk_category=INSUFFICIENT,
        explanation=f"No recommendation: {reason}. Review this item manually.", warnings=[reason],
    )


def recommend(
    item: ItemState,
    daily_forecast: np.ndarray | None,
    sigma_daily_error: float | None,
    policy: PolicySettings = PolicySettings(),
    period_sigma: float | None = None,
) -> Recommendation:
    """Full recommendation for one item.

    `sigma_daily_error`: std of past daily forecast errors for this item.
    `period_sigma`: optional measured std of past errors over the whole
    protection period; used instead of the sqrt(days) approximation when given.
    """
    if daily_forecast is None:
        return insufficient(item, "no forecast available")
    if sigma_daily_error is None and period_sigma is None:
        return insufficient(item, "no forecast-error history to size safety stock")

    position = f.inventory_position(item.on_hand, item.on_order, item.backorders)
    days = f.protection_period(item.lead_time_days, policy.review_period_days)
    lead_demand = f.forecast_demand(daily_forecast, item.lead_time_days)
    period_demand = f.forecast_demand(daily_forecast, days)
    mean_daily = period_demand / days

    if period_sigma is not None:
        sigma_period = period_sigma
        sigma_lead = period_sigma * (item.lead_time_days / days) ** 0.5
    else:
        sigma_period = f.demand_sigma_over_period(sigma_daily_error, days, mean_daily, item.sigma_lead_time_days)
        sigma_lead = f.demand_sigma_over_period(sigma_daily_error, item.lead_time_days, mean_daily,
                                                item.sigma_lead_time_days)

    safety = f.safety_stock(f.z_for_service_level(policy.service_level), sigma_period)
    reorder_pt = f.reorder_point(period_demand, safety)
    order_up_to = reorder_pt + cycle_quantity(mean_daily, item, policy)
    qty = f.order_quantity(position, order_up_to, item.min_order_qty, item.pack_size) if position <= reorder_pt else 0
    cover = position / mean_daily if mean_daily > 0 else None
    category = classify_risk(position, lead_demand, reorder_pt, order_up_to, cover, policy)

    warnings = []
    if item.demand_class in SLOW_CLASSES:
        warnings.append(f"{item.demand_class} demand: the normal approximation behind safety stock and"
                        " stockout probability is weak; treat them as indicative")
    if mean_daily == 0:
        warnings.append("forecast demand is zero")
    if item.unit_cost is None:
        warnings.append("unit cost unknown: order size uses cover days instead of EOQ, and cost is not estimated")

    rec = {
        "inventory_position": position, "protection_days": days,
        "forecast_lead_time_demand": lead_demand, "forecast_protection_demand": period_demand,
        "safety_stock": safety, "reorder_point": reorder_pt, "order_up_to": order_up_to,
        "suggested_qty": qty, "days_of_cover": cover, "risk_category": category,
    }
    return Recommendation(
        sku=item.sku, name=item.name, on_hand=item.on_hand, lead_time_days=item.lead_time_days,
        estimated_order_cost=qty * item.unit_cost if item.unit_cost is not None else None,
        stockout_probability=f.stockout_probability(position, lead_demand, sigma_lead),
        explanation=_explain(rec, item, policy), warnings=warnings, **rec,
    )
