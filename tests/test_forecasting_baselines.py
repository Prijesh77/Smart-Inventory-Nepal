import numpy as np
import pandas as pd
import pytest

from ml.evaluation import metrics
from ml.evaluation.backtest import build_sales_matrix, evaluate, rolling_origins, run_backtest
from ml.models.baselines import BASELINES, last_valid, moving_average, naive, seasonal_naive

NAN = np.nan


# ---------- metrics ----------

def test_metrics_hand_checked():
    actual = np.array([2, 0, 4, 2])
    forecast = np.array([3, 1, 2, 2])
    # errors (f - a): +1, +1, -2, 0
    assert metrics.mae(actual, forecast) == 1.0                        # 4 / 4
    assert metrics.rmse(actual, forecast) == pytest.approx(np.sqrt(6 / 4))
    assert metrics.wape(actual, forecast) == 0.5                       # 4 / 8
    assert metrics.bias(actual, forecast) == 0.0                       # 0 / 4
    assert metrics.bias_pct(actual, forecast) == 0.0


def test_metrics_skip_unavailable_days():
    actual = np.array([2, NAN, 2])
    forecast = np.array([1, 100, 1])
    assert metrics.mae(actual, forecast) == 1.0
    assert metrics.summarize(actual, forecast)["n"] == 2
    assert metrics.bias_pct(actual, forecast) == -0.5


def test_wape_undefined_when_no_sales():
    assert np.isnan(metrics.wape(np.array([0, 0]), np.array([1, 0])))


# ---------- baselines ----------

def test_last_valid_skips_trailing_nan():
    history = np.array([[1, 2, NAN], [NAN, NAN, NAN]])
    out = last_valid(history)
    assert out[0] == 2 and np.isnan(out[1])


def test_naive_repeats_last_day():
    assert naive(np.array([[1.0, 5.0]]), 3).tolist() == [[5, 5, 5]]


def test_seasonal_naive_repeats_last_week():
    week1 = [1, 1, 1, 1, 1, 1, 1]
    week2 = [1, 2, 3, 4, 5, 6, 7]
    out = seasonal_naive(np.array([week1 + week2], dtype=float), 9)
    assert out.tolist() == [[1, 2, 3, 4, 5, 6, 7, 1, 2]]


def test_seasonal_naive_uses_week_before_for_closed_day():
    week1 = [10, 20, 30, 40, 50, 60, 70]
    week2 = [1, 2, NAN, 4, 5, 6, 7]   # day 3 of last week was closed
    out = seasonal_naive(np.array([week1 + week2]), 7)
    assert out.tolist() == [[1, 2, 30, 4, 5, 6, 7]]


def test_moving_average_ignores_unavailable_days():
    history = np.array([[9, 2, NAN, 4]])
    # last 3 days: 2, NaN, 4 -> mean of available = 3
    assert moving_average(history, 2, window=3).tolist() == [[3, 3]]


def test_all_baselines_return_expected_shape():
    history = np.random.default_rng(0).poisson(2, size=(5, 60)).astype(float)
    for name, model in BASELINES.items():
        assert model(history, 28).shape == (5, 28), name


# ---------- backtest ----------

def test_rolling_origins_fit_inside_period():
    # Windows of 28 days every 28 days inside days 100..183 (84 days) -> 3 origins.
    assert rolling_origins(100, 183, 28, 28) == [100, 128, 156]


def test_build_sales_matrix_marks_unavailable_as_nan():
    daily = pd.DataFrame({
        "item_id": ["A", "A", "B"], "d_num": [1, 2, 2], "sales": [3, 0, 5],
        "is_available": [True, False, True],
    })
    m = build_sales_matrix(daily, last_day=2)
    assert m.loc["A"].tolist()[0] == 3 and np.isnan(m.loc["A", 2])
    assert np.isnan(m.loc["B", 1]) and m.loc["B", 2] == 5


def test_backtest_never_shows_the_future():
    matrix = pd.DataFrame(np.arange(1, 21, dtype=float).reshape(1, 20), index=["A"], columns=range(1, 21))
    seen = {}

    def spy(history, horizon):
        seen[history.shape[1]] = history[0, -1]
        return np.zeros((history.shape[0], horizon))

    out = run_backtest(matrix, {"spy": spy}, origins=[11, 15], horizon=3)
    # From origin 11 the model sees days 1..10, whose last value is 10.
    assert seen == {10: 10.0, 14: 14.0}
    first = out[out["origin"] == 11]
    assert first["d_num"].tolist() == [11, 12, 13]
    assert first["actual"].tolist() == [11, 12, 13]


def test_evaluate_groups_by_horizon_and_class():
    results = pd.DataFrame({
        "model": "m", "origin": 1, "item_id": ["A", "A", "B", "B"],
        "h": [1, 2, 1, 2], "d_num": [1, 2, 1, 2],
        "actual": [1.0, 1.0, 2.0, 2.0], "forecast": [1.0, 3.0, 2.0, 2.0],
    })
    out = evaluate(results, pd.Series({"A": "smooth", "B": "lumpy"}), horizons=[1, 2])
    row = out[(out["horizon"] == 2) & (out["demand_class"] == "smooth")].iloc[0]
    assert row["mae"] == 1.0 and row["n"] == 2
    row_all_h1 = out[(out["horizon"] == 1) & (out["demand_class"] == "all")].iloc[0]
    assert row_all_h1["mae"] == 0.0
