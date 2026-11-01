import pandas as pd
import pytest

from ml import config
from ml.data.clean_m5 import (
    INSUFFICIENT,
    add_prices,
    assign_split,
    classify_demand,
    melt_sales,
    stratified_sample,
    trim_before_launch,
)


def test_melt_sales_one_row_per_item_day():
    wide = pd.DataFrame({
        "item_id": ["A", "B"], "dept_id": ["D", "D"], "cat_id": ["C", "C"],
        "d_1": [1, 0], "d_2": [3, 5],
    })
    long = melt_sales(wide)
    assert len(long) == 4
    assert long.set_index(["item_id", "d_num"]).loc[("B", 2), "sales"] == 5


def test_trim_before_launch_uses_first_price_day():
    # Item A has no price on days 1-2, so those days are pre-launch and removed.
    long = pd.DataFrame({
        "item_id": ["A"] * 5,
        "d_num": [1, 2, 3, 4, 5],
        "sales": [0, 0, 2, 0, 1],
        "is_available": [False, False, True, False, True],
    })
    trimmed, stats = trim_before_launch(long)
    assert trimmed["d_num"].tolist() == [3, 4, 5]
    assert stats["rows_removed"] == 2
    assert stats["units_sold_before_launch"] == 0
    # Day 4 is a gap after launch: kept, still flagged unavailable (D2).
    assert not trimmed.loc[trimmed["d_num"] == 4, "is_available"].item()


def test_add_prices_flags_missing_weeks_and_christmas():
    long = pd.DataFrame({
        "item_id": ["A", "A", "A"],
        "wm_yr_wk": [100, 100, 101],
        "date": pd.to_datetime(["2013-12-24", "2013-12-25", "2014-01-01"]),
        "sales": [1, 0, 0],
    })
    prices = pd.DataFrame({"item_id": ["A"], "wm_yr_wk": [100], "sell_price": [2.5]})
    out = add_prices(long, prices)
    # Dec 25 has a price but the store is closed; week 101 has no price.
    assert out["is_store_open"].tolist() == [True, False, True]
    assert out["is_available"].tolist() == [True, False, False]


def test_assign_split_boundaries():
    days = pd.Series([1, config.TRAIN_END, config.VALIDATION_START, config.TEST_START - 1, config.TEST_START])
    assert assign_split(days).tolist() == ["train", "train", "validation", "validation", "test"]


def _train_rows(item_id: str, sales: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"item_id": item_id, "sales": sales, "is_available": True})


def test_classify_demand_hand_checked(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRAIN_DAYS", 4)
    monkeypatch.setattr(config, "MIN_NONZERO_DAYS", 2)
    train = pd.concat([
        _train_rows("smooth", [2, 2, 2, 2]),        # ADI 1.0, CV2 0
        _train_rows("erratic", [1, 9, 1, 9]),       # ADI 1.0, sizes 1,9: CV2 = (4/5)^2 = 0.64
        _train_rows("intermittent", [0, 3, 0, 3]),  # ADI 2.0, CV2 0
        _train_rows("lumpy", [0, 1, 0, 9]),         # ADI 2.0, CV2 0.64
        _train_rows("short", [1, 1]),               # only 2 days of history
    ])
    out = classify_demand(train).set_index("item_id")
    assert out.loc["erratic", "cv2"] == pytest.approx(0.64)
    assert out.loc["intermittent", "adi"] == 2.0
    assert out["demand_class"].to_dict() == {
        "erratic": "erratic",
        "intermittent": "intermittent",
        "lumpy": "lumpy",
        "short": INSUFFICIENT,
        "smooth": "smooth",
    }


def test_classify_demand_ignores_unavailable_days(monkeypatch):
    monkeypatch.setattr(config, "MIN_TRAIN_DAYS", 2)
    monkeypatch.setattr(config, "MIN_NONZERO_DAYS", 1)
    train = pd.DataFrame({
        "item_id": ["A"] * 4,
        "sales": [2, 0, 0, 2],
        "is_available": [True, False, False, True],
    })
    out = classify_demand(train).set_index("item_id")
    # The two unavailable zeros are not demand, so A sells every available day.
    assert out.loc["A", "adi"] == 1.0
    assert out.loc["A", "demand_class"] == "smooth"


def test_stratified_sample_is_reproducible_and_keeps_small_strata():
    classes = pd.DataFrame({
        "item_id": [f"i{n}" for n in range(30)],
        "cat_id": ["FOODS"] * 25 + ["HOBBIES"] * 5,
        "demand_class": ["smooth"] * 20 + ["lumpy"] * 5 + ["lumpy"] * 3 + [INSUFFICIENT] * 2,
    })
    a = stratified_sample(classes, size=10, min_per_stratum=3, seed=1)
    b = stratified_sample(classes, size=10, min_per_stratum=3, seed=1)
    assert a["item_id"].tolist() == b["item_id"].tolist()
    assert INSUFFICIENT not in set(a["demand_class"])
    counts = a.groupby(["cat_id", "demand_class"]).size().to_dict()
    # Proportional: 10 * 20/28 = 7; small strata lifted to the minimum of 3.
    assert counts == {("FOODS", "lumpy"): 3, ("FOODS", "smooth"): 7, ("HOBBIES", "lumpy"): 3}
