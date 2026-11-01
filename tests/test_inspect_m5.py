import numpy as np
import pandas as pd

from ml.data.inspect_m5 import Report, day_columns, inspect_cross_file, leading_zero_stats


def test_day_columns_sorted_numerically():
    assert day_columns(["id", "d_10", "d_2", "d_1", "dept"]) == ["d_1", "d_2", "d_10"]


def test_leading_zero_stats_hand_checked():
    # Row 1: first sale on day 3 -> 2 leading zeros, then one zero after.
    # Row 2: never sold -> 5 leading zeros.
    values = np.array([
        [0, 0, 4, 0, 1],
        [0, 0, 0, 0, 0],
    ])
    stats = leading_zero_stats(values)
    assert stats["never_sold"] == 1
    assert stats["leading_zero_share"] == 7 / 10
    assert stats["zero_share_all_cells"] == 8 / 10
    # 3 cells after row 1's first sale contain 1 zero.
    assert stats["zero_share_after_first_sale"] == 1 / 3
    assert stats["median_first_sale_day"] == 3


def test_cross_file_detects_sale_before_price():
    cal = pd.DataFrame({"d": ["d_1", "d_2", "d_3"], "wm_yr_wk": [100, 100, 101]})
    sales = pd.DataFrame({
        "id": ["A_S1", "B_S1"], "item_id": ["A", "B"], "store_id": ["S1", "S1"],
        "d_1": [1, 0], "d_2": [0, 0], "d_3": [0, 2],
    })
    prices = pd.DataFrame({
        "store_id": ["S1", "S1"], "item_id": ["A", "B"],
        "wm_yr_wk": [101, 101], "sell_price": [1.0, 2.0],
    })
    report = Report()
    inspect_cross_file(sales, prices, cal, report)
    text = "\n".join(report.lines)
    assert "first sale is before their first price week: 1" in text
    assert "first sale is in their first price week: 1 of 2" in text
