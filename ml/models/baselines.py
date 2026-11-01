"""Baseline forecasters.

Every forecaster has the same signature:

    forecast(history, horizon) -> array of shape (n_items, horizon)

`history` is a 2-D array (n_items x days) of daily sales ending on the day
before the forecast starts. NaN marks days when an item was unavailable
(not yet launched or store closed); those days are skipped, not treated as 0.

Baselines matter because a machine-learning model is only useful if it beats
them. On slow-moving items they are often hard to beat.
"""

from __future__ import annotations

import warnings
from functools import partial
from typing import Callable

import numpy as np

Forecaster = Callable[[np.ndarray, int], np.ndarray]


def last_valid(history: np.ndarray) -> np.ndarray:
    """Most recent non-NaN value per item (NaN if the item has no history)."""
    valid = ~np.isnan(history)
    idx = history.shape[1] - 1 - np.argmax(valid[:, ::-1], axis=1)
    out = history[np.arange(history.shape[0]), idx].astype(float)
    out[~valid.any(axis=1)] = np.nan
    return out


def _repeat(level: np.ndarray, horizon: int) -> np.ndarray:
    return np.repeat(level[:, None], horizon, axis=1)


def naive(history: np.ndarray, horizon: int) -> np.ndarray:
    """Every future day equals the last observed day."""
    return _repeat(last_valid(history), horizon)


def seasonal_naive(history: np.ndarray, horizon: int, season: int = 7) -> np.ndarray:
    """Every future day equals the same weekday last week.

    If that day was unavailable (e.g. Christmas), use the same weekday two
    weeks ago; if that is also missing, fall back to the naive value.
    """
    n = history.shape[1]
    last_season = history[:, n - season:]
    previous = history[:, n - 2 * season:n - season]
    pattern = np.where(np.isnan(last_season), previous, last_season)
    pattern = np.where(np.isnan(pattern), last_valid(history)[:, None], pattern)
    reps = -(-horizon // season)  # ceiling division
    return np.tile(pattern, (1, reps))[:, :horizon]


def moving_average(history: np.ndarray, horizon: int, window: int) -> np.ndarray:
    """Every future day equals the mean of the last `window` available days."""
    recent = history[:, -window:]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN rows
        level = np.nanmean(recent, axis=1)
    level = np.where(np.isnan(level), last_valid(history), level)
    return _repeat(level, horizon)


def zero(history: np.ndarray, horizon: int) -> np.ndarray:
    """Always forecast 0. A reference point, not a usable inventory forecast:
    it scores well on MAE for very slow items but would never trigger an order."""
    return np.zeros((history.shape[0], horizon))


BASELINES: dict[str, Forecaster] = {
    "naive": naive,
    "seasonal_naive_7": seasonal_naive,
    "moving_avg_7": partial(moving_average, window=7),
    "moving_avg_28": partial(moving_average, window=28),
    "zero_reference": zero,
}
