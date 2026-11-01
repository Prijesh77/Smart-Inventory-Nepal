"""Inventory formulas as small, independent, testable functions.

Policy used throughout: periodic review (R, s, S).
  - Every R days we look at the item.
  - If the inventory position is at or below the reorder point s, we order
    enough to bring it back up to the order-up-to level S.
  - Orders arrive L days later (the supplier lead time).

Between placing an order and the NEXT chance to order, L + R days pass. Stock
must cover that "protection period", so s is based on demand over L + R days.

References: Silver, Pyke & Thomas (2017) for the policy and formulas;
Prak, Teunter & Syntetos (2017) for using forecast errors (not raw demand
variability) when demand is forecast.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np


def inventory_position(on_hand: float, on_order: float, backorders: float = 0.0) -> float:
    """Stock we have or are already getting, minus demand we already owe.

    Inventory position = on-hand + on-order - backorders
    """
    for name, value in [("on_hand", on_hand), ("on_order", on_order), ("backorders", backorders)]:
        if value < 0:
            raise ValueError(f"{name} cannot be negative, got {value}")
    return on_hand + on_order - backorders


def protection_period(lead_time_days: int, review_period_days: int) -> int:
    """Days of demand an order must cover: lead time + review period."""
    if lead_time_days < 0 or review_period_days < 1:
        raise ValueError("lead time must be >= 0 and review period >= 1 day")
    return lead_time_days + review_period_days


def forecast_demand(daily_forecast: np.ndarray, days: int) -> float:
    """Expected demand over the next `days` days = sum of the daily forecasts."""
    daily_forecast = np.asarray(daily_forecast, dtype=float)
    if days > daily_forecast.size:
        raise ValueError(f"Need {days} days of forecast, only {daily_forecast.size} available")
    if np.isnan(daily_forecast[:days]).any():
        raise ValueError("Forecast contains missing values")
    return float(daily_forecast[:days].sum())


def z_for_service_level(service_level: float) -> float:
    """Safety factor z for a target cycle service level.

    Cycle service level = probability of NOT running out during one
    protection period. 95% -> z = 1.645. Assumes forecast errors over the
    period are roughly normal, which is weak for very slow items.
    """
    if not 0.5 <= service_level < 1:
        raise ValueError("service level must be in [0.5, 1)")
    return NormalDist().inv_cdf(service_level)


def demand_sigma_over_period(
    sigma_daily_error: float,
    days: int,
    mean_daily_demand: float = 0.0,
    sigma_lead_time_days: float = 0.0,
) -> float:
    """Standard deviation of demand uncertainty over a period of `days`.

    sigma = sqrt(days * sigma_e^2 + d^2 * sigma_LT^2)

    sigma_e is the standard deviation of DAILY FORECAST ERRORS, not of raw
    daily demand. The forecast already explains part of demand's variation
    (weekday effects, trends); only what it gets wrong needs safety stock.
    Using raw demand variability here as well would double-count.

    The first term assumes daily errors are independent. In practice errors
    are correlated (a forecast that is too low tends to stay too low), so
    this can understate risk; `period_sigma_from_errors` measures it directly.
    The second term adds uncertainty in the lead time itself.
    """
    if sigma_daily_error < 0 or sigma_lead_time_days < 0:
        raise ValueError("standard deviations cannot be negative")
    return math.sqrt(days * sigma_daily_error**2 + mean_daily_demand**2 * sigma_lead_time_days**2)


def period_sigma_from_errors(period_errors: np.ndarray, min_count: int = 8) -> float | None:
    """Empirical std of past forecast errors on period TOTALS (forecast - actual).

    Measures forecast error over the whole protection period directly, so
    correlated daily errors are captured. Returns None when there are too
    few past periods to trust the estimate.
    """
    errors = np.asarray(period_errors, dtype=float)
    errors = errors[~np.isnan(errors)]
    if errors.size < min_count:
        return None
    return float(np.sqrt(np.mean(errors**2)))  # RMSE: includes bias as well as spread


def safety_stock(z: float, sigma_period: float) -> float:
    """Extra stock held to absorb forecast error: SS = z x sigma."""
    if sigma_period < 0:
        raise ValueError("sigma cannot be negative")
    return max(0.0, z * sigma_period)


def reorder_point(expected_demand: float, safety: float) -> float:
    """s = expected demand over the protection period + safety stock."""
    return expected_demand + safety


def economic_order_quantity(
    annual_demand: float, ordering_cost: float, holding_cost_per_unit_year: float
) -> float:
    """Classic EOQ: the order size that balances ordering and holding cost.

    EOQ = sqrt(2 x D x K / h)
    Bigger orders -> fewer orders (less ordering cost) but more stock on the
    shelf (more holding cost). EOQ is where the two are balanced.
    """
    if annual_demand <= 0:
        return 0.0
    if ordering_cost < 0 or holding_cost_per_unit_year <= 0:
        raise ValueError("ordering cost must be >= 0 and holding cost > 0")
    return math.sqrt(2 * annual_demand * ordering_cost / holding_cost_per_unit_year)


def order_quantity(
    position: float, order_up_to: float, min_order_qty: int = 1, pack_size: int = 1
) -> int:
    """Units to order to bring the position up to S, respecting supplier rules.

    q = S - position, then raised to the minimum order quantity, then rounded
    UP to a whole number of packs. Returns 0 if no units are needed.
    """
    if min_order_qty < 1 or pack_size < 1:
        raise ValueError("minimum order quantity and pack size must be >= 1")
    needed = order_up_to - position
    if needed <= 0:
        return 0
    quantity = max(needed, min_order_qty)
    return int(math.ceil(quantity / pack_size) * pack_size)


def stockout_probability(position: float, expected_demand: float, sigma_period: float) -> float | None:
    """Estimated chance that demand over the period exceeds the inventory position.

    P(stockout) = 1 - Phi((position - expected demand) / sigma)

    A model estimate under a normal approximation, not an observed frequency.
    Returns None when sigma is 0 (no error information to estimate it).
    """
    if sigma_period <= 0:
        return None
    return 1.0 - NormalDist().cdf((position - expected_demand) / sigma_period)
