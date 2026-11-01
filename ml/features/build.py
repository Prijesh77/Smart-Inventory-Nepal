"""Leakage-safe features for direct multi-horizon forecasting.

One row = (item, origin, h): predict sales on target day = origin + h - 1.

Each row only uses two kinds of information:
  1. Sales statistics from days strictly BEFORE the origin (what a planner
     would know on the morning of the origin day).
  2. Facts about the target day that are known in advance: weekday, month,
     SNAP day, holiday/event type, and the planned price.

Because the same features are computed for every horizon h = 1..28, one model
forecasts all horizons at once ("direct" strategy). It never feeds its own
predictions back in, so errors do not compound across days.

Assumption (documented in docs/05): the price on the target day is known at
the origin. Retail prices are set weekly in advance, so this is realistic for
planned prices but not for unplanned markdowns.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.evaluation.backtest import build_sales_matrix
from ml.models.baselines import last_valid

EVENT_TYPES = ["Cultural", "National", "Religious", "Sporting"]
MIN_HISTORY_DAYS = 91           # longest look-back window used below
DAYS_SINCE_SALE_CAP = 365

FEATURES = [
    # forecast setup
    "h", "cat_code",
    # sales history before the origin
    "ma_7", "ma_28", "ma_91", "std_28", "zero_share_28", "days_since_sale", "same_wday_mean_4w",
    # known facts about the target day
    "wday", "month", "snap", "is_event", *[f"event_{e.lower()}" for e in EVENT_TYPES],
    "price_change", "price_vs_91d",
]


@dataclass(frozen=True)
class Panel:
    """All items' daily data as aligned arrays. Column j is day d_num = j + 1."""

    item_ids: np.ndarray
    cat_codes: np.ndarray
    sales: np.ndarray       # NaN where the item was unavailable
    price: np.ndarray       # NaN where the item was not listed
    calendar: pd.DataFrame  # indexed by d_num


def make_panel(daily: pd.DataFrame, last_day: int) -> Panel:
    """Turn the long daily table into aligned item x day arrays."""
    sales = build_sales_matrix(daily, last_day)
    ids = daily["item_id"].astype(str)
    price = (
        pd.DataFrame({"item_id": ids, "d_num": daily["d_num"], "sell_price": daily["sell_price"]})
        .pivot(index="item_id", columns="d_num", values="sell_price")
        .reindex(index=sales.index, columns=range(1, last_day + 1))
    )
    cats = daily.assign(item_id=ids).drop_duplicates("item_id").set_index("item_id")["cat_id"].astype(str)
    cat_codes = pd.Categorical(cats.reindex(sales.index), categories=sorted(cats.unique())).codes

    cal = (
        daily.drop_duplicates("d_num").set_index("d_num")[["wday", "month", "snap", "event_type_1"]]
        .reindex(range(1, last_day + 1))
    )
    event = cal["event_type_1"].astype(str)
    calendar = pd.DataFrame({
        "wday": cal["wday"], "month": cal["month"], "snap": cal["snap"],
        "is_event": cal["event_type_1"].notna().astype(int),
        **{f"event_{e.lower()}": (event == e).astype(int) for e in EVENT_TYPES},
    })
    return Panel(
        item_ids=sales.index.to_numpy(),
        cat_codes=np.asarray(cat_codes),
        sales=sales.to_numpy(dtype=float),
        price=price.to_numpy(dtype=float),
        calendar=calendar,
    )


def _nan_stat(func, values: np.ndarray, axis: int = -1) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN windows
        return func(values, axis=axis)


def origin_stats(panel: Panel, origin: int) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Per-item statistics using only days before `origin`.

    Returns (stats, weekday_profile). weekday_profile[:, k] is the mean of the
    last 4 values on the weekday that falls k days after the origin's weekday.
    """
    if origin - 1 < MIN_HISTORY_DAYS:
        raise ValueError(f"Origin d_{origin} needs at least {MIN_HISTORY_DAYS} days of history")
    hist = panel.sales[:, : origin - 1]
    n = hist.shape[1]

    last_28 = hist[:, -28:]
    available = ~np.isnan(last_28)
    with np.errstate(invalid="ignore", divide="ignore"):
        zero_share = ((last_28 == 0) & available).sum(axis=1) / available.sum(axis=1)

    sold = hist > 0
    ever_sold = sold.any(axis=1)
    # 1 = sold on the day before the origin.
    days_since = np.where(ever_sold, np.argmax(sold[:, ::-1], axis=1) + 1, DAYS_SINCE_SALE_CAP)

    # Positions n-7+k, n-14+k, n-21+k, n-28+k share the weekday of target day origin+k.
    positions = np.array([[n - 7 + k - 7 * j for j in range(4)] for k in range(7)])
    weekday_profile = _nan_stat(np.nanmean, hist[:, positions], axis=2)

    stats = {
        "ma_7": _nan_stat(np.nanmean, hist[:, -7:]),
        "ma_28": _nan_stat(np.nanmean, last_28),
        "ma_91": _nan_stat(np.nanmean, hist[:, -91:]),
        "std_28": _nan_stat(np.nanstd, last_28),
        "zero_share_28": zero_share,
        "days_since_sale": np.minimum(days_since, DAYS_SINCE_SALE_CAP).astype(float),
        "last_price": last_valid(panel.price[:, : origin - 1]),
        "price_91": _nan_stat(np.nanmean, panel.price[:, origin - 92: origin - 1]),
    }
    return stats, weekday_profile


def build_rows(panel: Panel, origins: Iterable[int], horizon: int) -> pd.DataFrame:
    """Feature rows for every item, origin and h = 1..horizon.

    The `target` column holds actual sales (NaN when unavailable). It is the
    only column that looks at or after the origin.
    """
    n_items = len(panel.item_ids)
    hs = np.arange(1, horizon + 1)
    item_idx = np.repeat(np.arange(n_items), horizon)
    h = np.tile(hs, n_items)
    frames = []
    for origin in origins:
        target_day = origin + h - 1
        if target_day.max() > panel.sales.shape[1]:
            raise ValueError(f"Origin d_{origin} + {horizon} days runs past the data")
        stats, profile = origin_stats(panel, origin)
        cal = panel.calendar.loc[target_day].reset_index(drop=True)
        target_price = panel.price[item_idx, target_day - 1]
        with np.errstate(invalid="ignore", divide="ignore"):
            price_change = target_price / stats["last_price"][item_idx]
            price_vs_91d = target_price / stats["price_91"][item_idx]
        frame = pd.DataFrame({
            "item_id": panel.item_ids[item_idx],
            "origin": origin,
            "d_num": target_day,
            "h": h,
            "cat_code": panel.cat_codes[item_idx],
            **{k: v[item_idx] for k, v in stats.items() if k not in ("last_price", "price_91")},
            "same_wday_mean_4w": profile[item_idx, (h - 1) % 7],
            "price_change": price_change,
            "price_vs_91d": price_vs_91d,
            "target": panel.sales[item_idx, target_day - 1],
        })
        frames.append(pd.concat([frame, cal], axis=1))
    rows = pd.concat(frames, ignore_index=True)
    # Unknown or missing price means "no planned change"; missing spread means "no variation".
    rows[["price_change", "price_vs_91d"]] = rows[["price_change", "price_vs_91d"]].fillna(1.0)
    rows["std_28"] = rows["std_28"].fillna(0.0)
    return rows
