"""Compare inventory policies fairly: cost at the SAME achieved fill rate.

Each policy is simulated at several service-level targets, giving a curve
of (fill rate, cost) points. Two policies are compared by reading both
curves at a common fill rate (linear interpolation between points).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def curve_value_at(fill: np.ndarray, value: np.ndarray, target: float) -> float:
    """Interpolate `value` at fill rate `target`; NaN outside the simulated range."""
    order = np.argsort(fill)
    fill, value = np.asarray(fill)[order], np.asarray(value)[order]
    if not fill[0] <= target <= fill[-1]:
        return float("nan")
    return float(np.interp(target, fill, value))


def overlap_midpoint(fill_a: np.ndarray, fill_b: np.ndarray) -> float:
    """Middle of the fill-rate range both policies reach (NaN if they never overlap)."""
    low = max(np.min(fill_a), np.min(fill_b))
    high = min(np.max(fill_a), np.max(fill_b))
    return (low + high) / 2 if low <= high else float("nan")


def matched_difference(summary: pd.DataFrame, policy: str, reference: str,
                       target: float | None = None, value: str = "total_cost") -> dict[str, float]:
    """Cost of `policy` vs `reference` at the same fill rate.

    `summary` has one row per (policy, service_level) for the item group of
    interest, with columns fill_rate and `value`. If `target` is None, the
    middle of the overlapping fill-rate range is used.
    """
    a = summary[summary["policy"] == policy]
    b = summary[summary["policy"] == reference]
    if target is None:
        target = overlap_midpoint(a["fill_rate"].to_numpy(), b["fill_rate"].to_numpy())
    if np.isnan(target):
        return {"fill_rate": target, "policy_value": np.nan, "reference_value": np.nan, "pct_diff": np.nan}
    va = curve_value_at(a["fill_rate"].to_numpy(), a[value].to_numpy(), target)
    vb = curve_value_at(b["fill_rate"].to_numpy(), b[value].to_numpy(), target)
    return {"fill_rate": target, "policy_value": va, "reference_value": vb, "pct_diff": (va - vb) / vb}


def bootstrap_matched(runs: pd.DataFrame, policy: str, reference: str, target: float,
                      n_boot: int = 1000, seed: int = 0, value: str = "total_cost") -> np.ndarray:
    """Bootstrap the matched % difference by resampling ITEMS with replacement.

    Each resample redraws which items are in the store (same draw for every
    policy and service level), re-pools fill rate and cost, and recomputes the
    matched difference at a fixed `target` fill rate. Resamples where either
    curve misses the target return NaN and should be dropped.
    """
    keys = ["policy", "service_level"]
    runs = runs[runs["policy"].isin([policy, reference])]
    items = np.sort(runs["item_id"].unique())
    pivot = {col: runs.pivot_table(index="item_id", columns=keys, values=col, aggfunc="sum").reindex(items)
             for col in ["units_sold", "demand", value]}
    columns = pivot["demand"].columns
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(len(items), np.full(len(items), 1 / len(items)), size=n_boot)   # B x items

    sold = weights @ pivot["units_sold"].to_numpy()
    demand = weights @ pivot["demand"].to_numpy()
    cost = weights @ pivot[value].to_numpy()
    fill = sold / demand

    pol = np.array([c[0] for c in columns])
    out = np.full(n_boot, np.nan)
    for b in range(n_boot):
        va = curve_value_at(fill[b, pol == policy], cost[b, pol == policy], target)
        vb = curve_value_at(fill[b, pol == reference], cost[b, pol == reference], target)
        out[b] = (va - vb) / vb
    return out
