"""The inventory replay (ml/inventory/simulate.py) on small hand-checkable cases."""

import numpy as np

from ml.inventory.simulate import replay

NAN = float("nan")


def test_sales_are_capped_by_stock_and_orders_arrive_after_the_lead_time():
    demand = np.array([[3.0, 3.0, 3.0, 3.0]])
    # start with 4 units; order 10 on day 0, which arrives at the start of day 2
    out = replay(demand, np.array([4.0]), lead=np.array([2]), review_days=7,
                 decide=lambda t, on_hand, on_order: np.array([10.0]))
    # day 0: sell 3 (1 left); day 1: want 3, sell 1 (stock-out); day 2: 10 arrive, sell 3; day 3: sell 3
    assert out.sold.tolist() == [10.0] and out.lost.tolist() == [2.0]
    assert out.stockout_days.tolist() == [1.0] and out.orders.tolist() == [1.0]
    assert out.stock_units_days.tolist() == [1 + 0 + 7 + 4]


def test_unknown_days_are_skipped_and_the_policy_sees_stock_on_order():
    seen = []

    def decide(t, on_hand, on_order):
        seen.append((t, on_hand[0], on_order[0]))
        return np.array([5.0 if t == 0 else 0.0])

    demand = np.array([[1.0, NAN, 1.0, 1.0]])
    out = replay(demand, np.array([2.0]), lead=np.array([3]), review_days=2, decide=decide)
    assert out.demand.tolist() == [3.0] and out.sold.tolist() == [3.0]   # day 1 is unknown: no demand, no sale
    assert seen == [(0, 2.0, 0.0), (2, 1.0, 5.0)]                       # on day 2 the 5 units are still on the way
