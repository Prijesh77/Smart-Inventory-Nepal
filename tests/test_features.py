import numpy as np
import pandas as pd
import pytest

from ml.features.build import FEATURES, MIN_HISTORY_DAYS, Panel, build_rows, origin_stats
from ml.models.forest import fit_forest, predict, training_rows

N_DAYS = 140


def make_test_panel(sales: np.ndarray, price: np.ndarray | None = None) -> Panel:
    n_items, n_days = sales.shape
    d = np.arange(1, n_days + 1)
    calendar = pd.DataFrame({
        "wday": (d - 1) % 7 + 1, "month": 1, "snap": 0, "is_event": 0,
        "event_cultural": 0, "event_national": 0, "event_religious": 0, "event_sporting": 0,
    }, index=d)
    return Panel(
        item_ids=np.array([f"I{i}" for i in range(n_items)]),
        cat_codes=np.zeros(n_items, dtype=int),
        sales=sales.astype(float),
        price=np.ones_like(sales, dtype=float) if price is None else price,
        calendar=calendar,
    )


def test_features_do_not_change_when_the_future_changes():
    rng = np.random.default_rng(0)
    sales = rng.poisson(3, size=(3, N_DAYS)).astype(float)
    origin = 100
    before = build_rows(make_test_panel(sales), [origin], horizon=14)

    changed = sales.copy()
    changed[:, origin - 1:] = 999   # rewrite the origin day and everything after
    after = build_rows(make_test_panel(changed), [origin], horizon=14)

    pd.testing.assert_frame_equal(before[FEATURES], after[FEATURES])
    assert (after["target"] == 999).all()   # only the target sees the future


def test_origin_stats_hand_checked():
    # 98 days of history: all 2s, except the final week, which is 0..6.
    history = np.full(98, 2.0)
    history[-7:] = [0, 1, 2, 3, 4, 5, 6]
    sales = np.concatenate([history, np.zeros(14)])[None, :]
    stats, profile = origin_stats(make_test_panel(sales), origin=99)
    assert stats["ma_7"][0] == 3.0
    assert stats["ma_28"][0] == pytest.approx((21 * 2 + 21) / 28)
    assert stats["days_since_sale"][0] == 1          # sold 6 units the day before
    assert stats["zero_share_28"][0] == pytest.approx(1 / 28)
    # Target day origin+0 shares the weekday of the value 0 a week ago,
    # plus three earlier weeks of 2s: (0 + 2 + 2 + 2) / 4.
    assert profile[0, 0] == 1.5
    assert profile[0, 6] == 3.0                      # (6 + 2 + 2 + 2) / 4


def test_same_weekday_feature_matches_target_weekday():
    sales = np.tile(np.arange(1, 8, dtype=float), N_DAYS // 7)[None, :]   # weekday k sells k units
    rows = build_rows(make_test_panel(sales), [100], horizon=14)
    actual_same_weekday = sales[0, rows["d_num"].to_numpy() - 1]
    assert np.allclose(rows["same_wday_mean_4w"], actual_same_weekday)


def test_price_change_uses_planned_target_price():
    sales = np.ones((1, N_DAYS))
    price = np.full((1, N_DAYS), 2.0)
    price[0, 104:] = 1.0                   # price halves from day 105
    rows = build_rows(make_test_panel(sales, price), [100], horizon=7)
    assert rows["price_change"].tolist() == [1, 1, 1, 1, 1, 0.5, 0.5]


def test_origin_needs_enough_history():
    with pytest.raises(ValueError):
        origin_stats(make_test_panel(np.ones((1, N_DAYS))), MIN_HISTORY_DAYS)


def test_forest_learns_weekday_pattern():
    sales = np.tile([1, 1, 1, 1, 1, 8, 8], N_DAYS // 7)[None, :].repeat(4, axis=0).astype(float)
    panel = make_test_panel(sales)
    train = training_rows(build_rows(panel, range(92, 106), horizon=14), last_target_day=119)
    params = {"n_estimators": 20, "min_samples_leaf": 1, "random_state": 0}
    model = fit_forest(train, params)
    test = build_rows(panel, [120], horizon=7)
    assert np.allclose(predict(model, test), test["target"], atol=0.5)
