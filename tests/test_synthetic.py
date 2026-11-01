import math

import numpy as np
import pandas as pd
import pytest

from ml.inventory.synthetic import SyntheticConfig, assign_suppliers, choose_pack_size, generate


@pytest.mark.parametrize("mean_daily, expected", [
    (0.3, 1),     # 7 days = 2.1 units -> single units
    (1.0, 6),     # 7 days = 7 units -> pack of 6 fits
    (2.0, 12),    # 14 units -> 12
    (10.0, 24),   # 70 units -> largest option
    (0.0, 1),     # no demand -> smallest option
])
def test_choose_pack_size(mean_daily, expected):
    assert choose_pack_size(mean_daily, (1, 6, 12, 24), max_cover_days=7) == expected


def test_assign_suppliers_uses_every_supplier_and_is_reproducible():
    cfg = SyntheticConfig()
    depts = [f"D{i}" for i in range(7)]
    a = assign_suppliers(depts, cfg.suppliers, np.random.default_rng(1))
    b = assign_suppliers(depts, cfg.suppliers, np.random.default_rng(1))
    assert a == b
    assert set(a.values()) == {s.supplier_id for s in cfg.suppliers}


def make_daily(test_start: int = 50, days: int = 60) -> pd.DataFrame:
    rows = []
    for item, dept, price, rate in [("A", "FOODS_1", 2.0, 4), ("B", "HOBBIES_1", 10.0, 1)]:
        for d in range(1, days + 1):
            rows.append({"item_id": item, "dept_id": dept, "cat_id": dept.split("_")[0],
                         "demand_class": "smooth", "d_num": d, "sales": rate,
                         "sell_price": price, "is_available": True})
    return pd.DataFrame(rows)


def test_generate_hand_checked():
    cfg = SyntheticConfig(recent_days=28, initial_cover_days=21)
    items, _ = generate(make_daily(), cfg, test_start=50)
    a = items.set_index("item_id").loc["A"]
    assert 0.60 * 2.0 <= a["unit_cost"] <= 0.70 * 2.0
    assert a["pack_size"] == 24 and a["min_order_qty"] == 24     # 4/day x 7 = 28 -> 24
    assert a["initial_on_hand"] == 84                            # 4/day x 21 days
    assert items.loc[items["item_id"] == "B", "pack_size"].item() == 6


def test_generate_ignores_the_test_year():
    daily = make_daily()
    changed = daily.copy()
    future = changed["d_num"] >= 50
    changed.loc[future, "sales"] = 999
    changed.loc[future, "sell_price"] = 999.0
    cfg = SyntheticConfig()
    pd.testing.assert_frame_equal(generate(daily, cfg, 50)[0], generate(changed, cfg, 50)[0])


def test_generate_is_reproducible():
    cfg = SyntheticConfig()
    pd.testing.assert_frame_equal(generate(make_daily(), cfg, 50)[0], generate(make_daily(), cfg, 50)[0])
