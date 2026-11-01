"""Rolling-origin backtesting.

The idea in simple terms: pretend we are standing on a past date (the
"origin"), give each model only the sales before that date, ask for the next
28 days, then compare with what really happened. Repeat for several origins
so one unusual month does not decide the result.

         history (known)          | forecast window
    d_1 ..................... o-1 | o ... o+27
                                  ^ origin
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from ml.evaluation.metrics import summarize
from ml.models.baselines import Forecaster


def build_sales_matrix(daily: pd.DataFrame, last_day: int) -> pd.DataFrame:
    """Items x day matrix of sales, NaN wherever the item was unavailable.

    Columns are d_num 1..last_day so column position = day number - 1.
    """
    sales = daily["sales"].astype(float).where(daily["is_available"])
    matrix = (
        pd.DataFrame({"item_id": daily["item_id"].astype(str), "d_num": daily["d_num"], "sales": sales})
        .pivot(index="item_id", columns="d_num", values="sales")
        .reindex(columns=range(1, last_day + 1))
        .sort_index()
    )
    return matrix


def rolling_origins(first_origin: int, last_target_day: int, horizon: int, step: int) -> list[int]:
    """Origins from `first_origin` every `step` days whose full window ends by `last_target_day`."""
    return list(range(first_origin, last_target_day - horizon + 2, step))


def run_backtest(
    matrix: pd.DataFrame,
    forecasters: Mapping[str, Forecaster],
    origins: Iterable[int],
    horizon: int,
) -> pd.DataFrame:
    """Forecast from every origin with every model; return one row per item-day-model.

    Only columns strictly before the origin are passed to a model, so no
    model can see the days it is forecasting.
    """
    values = matrix.to_numpy()
    items = matrix.index.to_numpy()
    rows = []
    for origin in origins:
        history = values[:, : origin - 1]               # days 1 .. origin-1
        actual = values[:, origin - 1: origin - 1 + horizon]
        if actual.shape[1] < horizon:
            raise ValueError(f"Origin d_{origin} needs {horizon} days of actuals")
        for name, forecaster in forecasters.items():
            forecast = forecaster(history, horizon)
            if forecast.shape != actual.shape:
                raise ValueError(f"{name} returned shape {forecast.shape}, expected {actual.shape}")
            rows.append(pd.DataFrame({
                "model": name,
                "origin": origin,
                "item_id": np.repeat(items, horizon),
                "h": np.tile(np.arange(1, horizon + 1), len(items)),
                "d_num": np.tile(np.arange(origin, origin + horizon), len(items)),
                "actual": actual.ravel(),
                "forecast": forecast.ravel(),
            }))
    return pd.concat(rows, ignore_index=True)


def evaluate(
    results: pd.DataFrame, item_classes: pd.Series, horizons: Iterable[int]
) -> pd.DataFrame:
    """Metrics per model, cumulative horizon (days 1..H) and demand class.

    `item_classes` maps item_id -> demand class. An extra class "all" pools
    every item. Unavailable days (actual = NaN) are excluded by the metrics.
    """
    results = results.assign(demand_class=results["item_id"].map(item_classes))
    records = []
    for horizon in horizons:
        window = results[results["h"] <= horizon]
        groups = [("all", window)] + list(window.groupby("demand_class"))
        for cls, part in groups:
            for model, sub in part.groupby("model", sort=False):
                records.append({
                    "model": model, "horizon": horizon, "demand_class": cls,
                    **summarize(sub["actual"].to_numpy(), sub["forecast"].to_numpy()),
                })
    return pd.DataFrame(records)


def best_model_share(results: pd.DataFrame, horizon: int, exclude: Iterable[str] = ()) -> pd.Series:
    """Share of items for which each model has the lowest MAE over days 1..horizon."""
    window = results[(results["h"] <= horizon) & results["actual"].notna() & ~results["model"].isin(list(exclude))]
    per_item = (
        window.assign(abs_err=(window["forecast"] - window["actual"]).abs())
        .groupby(["item_id", "model"])["abs_err"].mean()
        .unstack()
    )
    return per_item.idxmin(axis=1).value_counts(normalize=True).rename("share_of_items")
