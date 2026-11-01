"""Forecast accuracy metrics.

All functions ignore positions where the actual or the forecast is NaN, so
unavailable days (not on sale, store closed) never count as errors.

Error convention: error = forecast - actual. Positive bias means over-forecasting.

Why no MAPE: it divides each error by the actual value, which is undefined on
the ~50% of item-days with zero sales (Hyndman & Koehler, 2006).
"""

from __future__ import annotations

import numpy as np


def _clean(actual: np.ndarray, forecast: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    keep = ~(np.isnan(actual) | np.isnan(forecast))
    return actual[keep], forecast[keep]


def mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean absolute error, in units per day."""
    a, f = _clean(actual, forecast)
    return float(np.mean(np.abs(f - a))) if a.size else float("nan")


def rmse(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Root mean squared error; punishes large misses more than MAE."""
    a, f = _clean(actual, forecast)
    return float(np.sqrt(np.mean((f - a) ** 2))) if a.size else float("nan")


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Weighted absolute percentage error = sum|error| / sum(actual).

    Pooling errors before dividing avoids dividing by zero on single days.
    Limitations: undefined when total actual sales are zero, and fast-moving
    items dominate the result because they contribute most units.
    """
    a, f = _clean(actual, forecast)
    total = a.sum()
    return float(np.abs(f - a).sum() / total) if total > 0 else float("nan")


def bias(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean signed error in units per day (positive = over-forecast)."""
    a, f = _clean(actual, forecast)
    return float(np.mean(f - a)) if a.size else float("nan")


def bias_pct(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Total signed error as a share of total actual sales."""
    a, f = _clean(actual, forecast)
    total = a.sum()
    return float((f - a).sum() / total) if total > 0 else float("nan")


def summarize(actual: np.ndarray, forecast: np.ndarray) -> dict[str, float]:
    """All metrics at once, plus the number of item-days evaluated."""
    a, _ = _clean(actual, forecast)
    return {
        "n": int(a.size),
        "mae": mae(actual, forecast),
        "rmse": rmse(actual, forecast),
        "wape": wape(actual, forecast),
        "bias": bias(actual, forecast),
        "bias_pct": bias_pct(actual, forecast),
    }
