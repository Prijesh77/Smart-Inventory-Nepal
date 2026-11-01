import numpy as np
import pandas as pd
import pytest

from ml.evaluation.inventory_compare import (
    bootstrap_matched, curve_value_at, matched_difference, overlap_midpoint,
)


def test_curve_value_at_interpolates_and_refuses_to_extrapolate():
    fill = np.array([0.98, 0.99, 0.97])          # unsorted on purpose
    cost = np.array([200.0, 300.0, 100.0])
    assert curve_value_at(fill, cost, 0.985) == pytest.approx(250)
    assert np.isnan(curve_value_at(fill, cost, 0.995))


def test_overlap_midpoint():
    assert overlap_midpoint(np.array([0.97, 0.99]), np.array([0.98, 0.995])) == pytest.approx(0.985)
    assert np.isnan(overlap_midpoint(np.array([0.90, 0.95]), np.array([0.96, 0.99])))


def test_matched_difference_hand_checked():
    # A reaches 98.5% for 225; B reaches 98.5% for 250 -> A is 10% cheaper.
    summary = pd.DataFrame({
        "policy": ["A", "A", "B", "B"],
        "fill_rate": [0.98, 0.99, 0.98, 0.99],
        "total_cost": [200.0, 250.0, 220.0, 280.0],
    })
    out = matched_difference(summary, "A", "B")
    assert out["fill_rate"] == pytest.approx(0.985)
    assert out["policy_value"] == pytest.approx(225)
    assert out["reference_value"] == pytest.approx(250)
    assert out["pct_diff"] == pytest.approx(-0.10)


def _runs(cost_a: float, cost_b: float) -> pd.DataFrame:
    rows = []
    for item in ["i1", "i2", "i3"]:
        for policy, cost in [("A", cost_a), ("B", cost_b)]:
            for sl, sold in [(0.9, 98), (0.99, 100)]:
                rows.append({"policy": policy, "service_level": sl, "item_id": item,
                             "units_sold": sold, "demand": 100, "total_cost": cost + sl * 10})
    return pd.DataFrame(rows)


def test_bootstrap_identical_items_gives_no_spread():
    # Every item is identical, so every resample gives the same answer.
    draws = bootstrap_matched(_runs(10, 20), "A", "B", target=0.99, n_boot=50, seed=1)
    # Fill is 98% at the 0.9 target and 100% at 0.99, so 99% is halfway:
    # A = (19 + 19.9) / 2 = 19.45, B = (29 + 29.9) / 2 = 29.45.
    expected = (19.45 - 29.45) / 29.45
    assert np.allclose(draws, expected)


def test_bootstrap_is_reproducible():
    runs = _runs(10, 20)
    runs.loc[runs["item_id"] == "i2", "total_cost"] *= 3
    a = bootstrap_matched(runs, "A", "B", target=0.99, n_boot=30, seed=7)
    b = bootstrap_matched(runs, "A", "B", target=0.99, n_boot=30, seed=7)
    assert np.array_equal(a, b)
