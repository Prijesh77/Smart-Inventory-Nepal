"""Inventory engine tests. Every expected value can be checked with a calculator;
the worked example is written out step by step in docs/06_inventory_engine.md."""

import math
from dataclasses import replace

import numpy as np
import pytest

from ml.inventory import formulas as f
from ml.inventory.recommend import (
    CRITICAL, EXCESS, HEALTHY, INSUFFICIENT, REORDER_SOON,
    ItemState, PolicySettings, classify_risk, cycle_quantity, recommend,
)

Z95 = 1.6448536269514722


# ---------- formulas ----------

def test_inventory_position():
    assert f.inventory_position(on_hand=20, on_order=10, backorders=5) == 25
    with pytest.raises(ValueError):
        f.inventory_position(-1, 0)


def test_protection_period_and_forecast_demand():
    assert f.protection_period(5, 7) == 12
    assert f.forecast_demand(np.array([1, 2, 3, 4]), 3) == 6
    with pytest.raises(ValueError):
        f.forecast_demand(np.array([1, 2]), 3)          # not enough forecast days


def test_z_for_service_level():
    assert f.z_for_service_level(0.95) == pytest.approx(Z95)
    assert f.z_for_service_level(0.5) == pytest.approx(0)
    with pytest.raises(ValueError):
        f.z_for_service_level(1.0)


def test_demand_sigma_with_and_without_lead_time_uncertainty():
    # Fixed lead time: sqrt(4 days x 2^2) = 4
    assert f.demand_sigma_over_period(2, 4) == 4
    # Uncertain lead time: sqrt(4 x 2^2 + 5^2 x 1^2) = sqrt(41)
    assert f.demand_sigma_over_period(2, 4, mean_daily_demand=5, sigma_lead_time_days=1) == pytest.approx(math.sqrt(41))


def test_period_sigma_from_errors_needs_enough_history():
    assert f.period_sigma_from_errors(np.array([3, -3, 3, -3]), min_count=8) is None
    assert f.period_sigma_from_errors(np.array([3, -3] * 4)) == 3.0
    # Bias is included: errors of +2 every time give 2, not 0.
    assert f.period_sigma_from_errors(np.full(8, 2.0)) == 2.0


def test_safety_stock_and_reorder_point():
    assert f.safety_stock(Z95, 10) == pytest.approx(16.449, abs=1e-3)
    assert f.safety_stock(Z95, 0) == 0
    assert f.reorder_point(48, 11.4) == pytest.approx(59.4)


def test_eoq_hand_checked():
    # sqrt(2 x 1000 x 50 / 4) = sqrt(25000) = 158.11
    assert f.economic_order_quantity(1000, 50, 4) == pytest.approx(158.114, abs=1e-3)
    assert f.economic_order_quantity(0, 50, 4) == 0


@pytest.mark.parametrize("position, up_to, moq, pack, expected", [
    (30, 30, 1, 1, 0),        # nothing needed
    (40, 30, 1, 1, 0),        # already above S
    (30, 55, 1, 1, 25),       # plain difference
    (30, 55, 30, 1, 30),      # raised to the minimum order quantity
    (30, 55, 30, 12, 36),     # 30 rounded up to 3 packs of 12
    (30, 55.2, 1, 1, 26),     # fractional need rounds up
])
def test_order_quantity_rounding(position, up_to, moq, pack, expected):
    assert f.order_quantity(position, up_to, moq, pack) == expected


def test_stockout_probability():
    assert f.stockout_probability(20, 20, 5) == pytest.approx(0.5)
    assert f.stockout_probability(20 + Z95 * 5, 20, 5) == pytest.approx(0.05)
    assert f.stockout_probability(20, 20, 0) is None


# ---------- recommendation ----------

POLICY = PolicySettings(service_level=0.95, review_period_days=7, ordering_cost=10,
                        holding_cost_rate=0.25, min_cycle_days=7, max_cycle_days=28, excess_cover_days=60)
ITEM = ItemState(sku="FOODS_3_001", name="Example item", on_hand=20, on_order=10, lead_time_days=5,
                 unit_cost=25.0, min_order_qty=24, pack_size=12)
FLAT_4 = np.full(28, 4.0)


def test_worked_example_matches_docs():
    rec = recommend(ITEM, FLAT_4, sigma_daily_error=2.0, policy=POLICY)
    sigma_12 = 2 * math.sqrt(12)                                   # 6.928
    eoq = math.sqrt(2 * 4 * 365 * 10 / (0.25 * 25))                # 68.35
    assert rec.inventory_position == 30
    assert rec.protection_days == 12
    assert rec.forecast_lead_time_demand == 20
    assert rec.forecast_protection_demand == 48
    assert rec.safety_stock == pytest.approx(Z95 * sigma_12)        # 11.40
    assert rec.reorder_point == pytest.approx(48 + Z95 * sigma_12)  # 59.40
    assert rec.order_up_to == pytest.approx(rec.reorder_point + eoq)  # 127.75
    assert rec.suggested_qty == 108                                # 97.75 -> 9 packs of 12
    assert rec.estimated_order_cost == 2700
    assert rec.days_of_cover == 7.5
    assert rec.risk_category == REORDER_SOON
    assert rec.stockout_probability == pytest.approx(1 - 0.98733, abs=1e-4)  # z = 10 / 4.472
    assert "Order 108 units" in rec.explanation


def test_cycle_quantity_is_capped_for_cheap_items():
    cheap = ItemState(sku="X", name="X", on_hand=0, on_order=0, lead_time_days=5, unit_cost=0.5)
    # EOQ would be sqrt(2 x 1460 x 10 / 0.125) = 483 units = 121 days; capped at 28 days x 4 = 112
    assert cycle_quantity(4.0, cheap, POLICY) == 112


def test_cycle_quantity_without_cost_uses_review_cover():
    no_cost = ItemState(sku="X", name="X", on_hand=0, on_order=0, lead_time_days=5)
    assert cycle_quantity(4.0, no_cost, POLICY) == 28


def test_no_order_above_reorder_point():
    rec = recommend(replace(ITEM, on_hand=80), FLAT_4, 2.0, POLICY)   # position 90 > s = 59.4
    assert rec.suggested_qty == 0 and rec.risk_category == HEALTHY


@pytest.mark.parametrize("position, expected", [
    (15, CRITICAL),        # below lead-time demand of 20
    (20, REORDER_SOON),    # covers lead time, but at/below s
    (59, REORDER_SOON),
    (100, HEALTHY),        # above s, below S
    (300, EXCESS),         # above S and 75 days of cover
])
def test_classify_risk_rules(position, expected):
    cover = position / 4
    assert classify_risk(position, 20, 59.4, 127.75, cover, POLICY) == expected


def test_above_order_up_to_but_short_cover_is_not_excess():
    # Above S (127.75) but only 50 days of cover (< 60) -> healthy
    assert classify_risk(200, 20, 59.4, 127.75, 50, POLICY) == HEALTHY


def test_insufficient_data_when_no_forecast_or_error_history():
    assert recommend(ITEM, None, 2.0).risk_category == INSUFFICIENT
    rec = recommend(ITEM, FLAT_4, None)
    assert rec.risk_category == INSUFFICIENT and rec.suggested_qty == 0
    assert "safety stock" in rec.explanation


def test_measured_period_sigma_overrides_square_root_rule():
    rec = recommend(ITEM, FLAT_4, sigma_daily_error=2.0, policy=POLICY, period_sigma=10.0)
    assert rec.safety_stock == pytest.approx(Z95 * 10)


def test_slow_item_and_unknown_cost_warnings():
    slow = ItemState(sku="X", name="X", on_hand=1, on_order=0, lead_time_days=3, demand_class="intermittent")
    rec = recommend(slow, np.full(28, 0.5), 0.8, POLICY)
    assert any("intermittent" in w for w in rec.warnings)
    assert any("unit cost unknown" in w for w in rec.warnings)
    assert rec.estimated_order_cost is None
