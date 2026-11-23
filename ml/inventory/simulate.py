"""Replay an ordering policy over past days to see what it would have done to the shop.

Each day: deliveries due that day arrive, customers buy what they want (the day's actual sales) up to what is on
the shelf, and anything they could not get is a lost sale. On review days the policy looks at stock and decides
how much to order; an order arrives `lead` days later. Days with unknown demand (NaN) are skipped.

Pure numpy, no database: the script backend/scripts/simulate_policies.py feeds it real shop data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

# decide(day index, on_hand, on_order) -> units to order per item (0 = no order)
Policy = Callable[[int, np.ndarray, np.ndarray], np.ndarray]


@dataclass(frozen=True)
class Outcome:
    demand: np.ndarray          # units customers wanted, per item (known days only)
    sold: np.ndarray            # units actually sold
    stockout_days: np.ndarray   # days on which some demand was not met, per item
    stock_units_days: np.ndarray  # sum over days of units on the shelf (end of day), per item
    orders: np.ndarray          # number of orders placed, per item
    units_ordered: np.ndarray
    days: int

    @property
    def lost(self) -> np.ndarray:
        return self.demand - self.sold


def replay(demand: np.ndarray, start_stock: np.ndarray, lead: np.ndarray, review_days: int, decide: Policy) -> Outcome:
    n, days = demand.shape
    on_hand = start_stock.astype(float).copy()
    arrivals = np.zeros((n, days + int(lead.max()) + 1))
    out = {k: np.zeros(n) for k in ("demand", "sold", "stockout_days", "stock_units_days", "orders", "units_ordered")}
    rows = np.arange(n)
    for t in range(days):
        on_hand += arrivals[:, t]
        if t % review_days == 0:
            on_order = arrivals[:, t + 1:].sum(axis=1)
            qty = np.maximum(np.asarray(decide(t, on_hand.copy(), on_order), dtype=float), 0)
            arrivals[rows, t + lead] += qty
            out["orders"] += qty > 0
            out["units_ordered"] += qty
        want = demand[:, t]
        known = ~np.isnan(want)
        want = np.where(known, want, 0.0)
        sold = np.minimum(on_hand, want)
        on_hand -= sold
        out["demand"] += want
        out["sold"] += sold
        out["stockout_days"] += (want - sold) > 1e-9
        out["stock_units_days"] += on_hand
    return Outcome(days=days, **out)
