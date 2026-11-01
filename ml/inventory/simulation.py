"""Day-by-day inventory simulation for one item.

The simulator only knows the mechanics of stock moving in and out. The
ordering decision is passed in as a function, so every policy runs through
exactly the same mechanics, demand and starting stock.

Order of events each day t:
  1. Morning: orders due today arrive and go on the shelf.
  2. Review (only on review days): the policy sees today's on-hand and
     on-order stock (no sales from today yet) and may place an order.
     An order placed on day t arrives on the morning of day t + lead time.
  3. Customers buy: sold = min(demand, on hand). Unmet demand is a LOST
     SALE (shoppers buy elsewhere); nothing is backordered.
  4. Evening: holding cost is charged on the stock left on the shelf.

All results are SIMULATED: demand comes from real M5 sales, but stock,
costs and lead times are assumptions (docs/07_synthetic_inventory.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# decide(t, on_hand, on_order) -> units to order
Decision = Callable[[int, float, float], int]


@dataclass(frozen=True)
class SimItem:
    item_id: str
    unit_cost: float
    unit_price: float
    initial_on_hand: float


@dataclass(frozen=True)
class CostSettings:
    ordering_cost: float = 10.0        # per order placed
    holding_cost_rate: float = 0.25    # per year, share of unit cost


def simulate_item(
    demand: np.ndarray,
    review: np.ndarray,
    lead_times: np.ndarray,
    item: SimItem,
    decide: Decision,
    costs: CostSettings = CostSettings(),
) -> dict[str, float]:
    """Run one item through the period and return summary measures.

    demand:     units customers want each day (0 on closed days)
    review:     True on days the policy may order
    lead_times: lead time in days for an order placed on each day (>= 1)
    """
    demand = np.asarray(demand, dtype=float)
    n = demand.size
    if review.size != n or lead_times.size != n:
        raise ValueError("demand, review and lead_times must have the same length")
    if (lead_times < 1).any():
        raise ValueError("lead times must be at least 1 day")

    arrivals = np.zeros(n + int(lead_times.max()) + 1)
    on_hand, on_order = float(item.initial_on_hand), 0.0
    end_stock = np.zeros(n)
    lost = np.zeros(n)
    n_orders, units_ordered = 0, 0.0

    for t in range(n):
        received = arrivals[t]
        on_hand += received
        on_order -= received

        if review[t]:
            qty = decide(t, on_hand, on_order)
            if qty < 0:
                raise ValueError(f"policy returned a negative order ({qty}) on day {t}")
            if qty > 0:
                arrivals[t + int(lead_times[t])] += qty
                on_order += qty
                n_orders += 1
                units_ordered += qty

        sold = min(demand[t], on_hand)
        lost[t] = demand[t] - sold
        on_hand -= sold
        end_stock[t] = on_hand

    total_demand = demand.sum()
    units_lost = lost.sum()
    daily_holding_rate = costs.holding_cost_rate / 365
    holding_cost = end_stock.sum() * item.unit_cost * daily_holding_rate
    ordering_cost = n_orders * costs.ordering_cost
    return {
        "demand": total_demand,
        "units_sold": total_demand - units_lost,
        "units_lost": units_lost,
        "fill_rate": (total_demand - units_lost) / total_demand if total_demand > 0 else float("nan"),
        "stockout_days": int((lost > 0).sum()),
        "days": n,
        "avg_on_hand": end_stock.mean(),
        "avg_inventory_value": end_stock.mean() * item.unit_cost,
        "n_orders": n_orders,
        "units_ordered": units_ordered,
        "holding_cost": holding_cost,
        "ordering_cost": ordering_cost,
        "total_cost": holding_cost + ordering_cost,
        "lost_margin": units_lost * max(item.unit_price - item.unit_cost, 0.0),
        "ending_on_hand": on_hand,
    }
