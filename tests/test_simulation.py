"""Simulator tests on tiny cases that can be traced by hand, day by day."""

import numpy as np
import pytest

from ml.inventory.simulation import CostSettings, SimItem, simulate_item

ITEM = SimItem(item_id="A", unit_cost=3.65, unit_price=5.0, initial_on_hand=5)
COSTS = CostSettings(ordering_cost=10, holding_cost_rate=0.25)


def never(t, on_hand, on_order):
    return 0


def run(demand, decide=never, review=None, lead=2, item=ITEM):
    n = len(demand)
    review = np.ones(n, dtype=bool) if review is None else np.asarray(review)
    return simulate_item(np.array(demand, dtype=float), review, np.full(n, lead), item, decide, COSTS)


def test_lost_sales_when_stock_runs_out():
    # Start 5. Day 0: sell 3 (2 left). Day 1: want 4, sell 2, lose 2. Day 2: want 1, lose 1.
    out = run([3, 4, 1])
    assert out["units_sold"] == 5
    assert out["units_lost"] == 3
    assert out["fill_rate"] == pytest.approx(5 / 8)
    assert out["stockout_days"] == 2


def test_order_arrives_after_lead_time_before_sales():
    calls = []

    def order_once(t, on_hand, on_order):
        calls.append((t, on_hand, on_order))
        return 10 if t == 0 else 0

    # Order 10 on day 0 with lead time 2 -> on the shelf the morning of day 2.
    out = run([2, 2, 4, 1], decide=order_once)
    # Day 0: 5-2=3. Day 1: 3-2=1. Day 2: +10 -> 11, sell 4 -> 7. Day 3: sell 1 -> 6.
    assert out["units_lost"] == 0
    assert out["ending_on_hand"] == 6
    assert out["n_orders"] == 1
    # The policy saw the pending order on day 1 and the arrival on day 2.
    assert calls[1] == (1, 3, 10)
    assert calls[2] == (2, 11, 0)


def test_policy_only_called_on_review_days():
    seen = []

    def spy(t, on_hand, on_order):
        seen.append(t)
        return 0

    run([0] * 10, decide=spy, review=[i % 7 == 0 for i in range(10)])
    assert seen == [0, 7]


def test_holding_and_ordering_cost_hand_checked():
    # 5 units held all 4 days -> 20 unit-days x $3.65 x 0.25 / 365 = $0.05
    out = run([0, 0, 0, 0])
    assert out["holding_cost"] == pytest.approx(20 * 3.65 * 0.25 / 365)
    assert out["avg_on_hand"] == 5
    assert out["avg_inventory_value"] == pytest.approx(5 * 3.65)

    out = run([0, 0, 0, 0], decide=lambda t, h, o: 1 if t < 2 else 0)
    assert out["n_orders"] == 2 and out["ordering_cost"] == 20


def test_lost_margin_uses_price_minus_cost():
    out = run([7])
    assert out["units_lost"] == 2
    assert out["lost_margin"] == pytest.approx(2 * (5.0 - 3.65))


def test_orders_arriving_after_the_period_are_still_on_order():
    out = run([0, 0], decide=lambda t, h, o: 4 if t == 1 else 0, lead=5)
    assert out["units_ordered"] == 4 and out["ending_on_hand"] == 5


def test_period_errors_sum_each_items_own_protection_period():
    from ml.experiments.run_simulation import period_errors

    forecast = np.array([[1.0, 1, 1, 1], [2, 2, 2, 2]])
    actual = np.array([[0.0, 3, 0, 0], [1, 1, 1, 1]])
    # Item 0 uses 2 days: (1+1) - (0+3) = -1. Item 1 uses 3 days: 6 - 3 = 3.
    assert period_errors(forecast, actual, np.array([2, 3])).tolist() == [-1, 3]
    # Works with a leading origin dimension too.
    stacked = period_errors(np.stack([forecast, forecast]), np.stack([actual, actual]), np.array([2, 3]))
    assert stacked.tolist() == [[-1, 3], [-1, 3]]


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        run([1, 1], lead=0)
    with pytest.raises(ValueError):
        run([1], decide=lambda t, h, o: -1)
