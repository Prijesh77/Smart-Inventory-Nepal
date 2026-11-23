"""Forecasters made for intermittent demand (many days with no sale).

Both follow the baselines' signature, forecast(history, horizon) -> (n_items, horizon), and skip NaN days.

Croston's idea: forecast "how much is sold when it sells" and "how often it sells" separately, each with
exponential smoothing, and divide one by the other.
  SBA  Syntetos-Boylan approximation: Croston times (1 - alpha / 2), which removes Croston's known upward bias.
  TSB  Teunter-Syntetos-Babai: smooths the probability of a sale every day (not only on sale days), so the
       forecast falls when an item stops selling. Better for items that become obsolete.
"""

from __future__ import annotations

import numpy as np


def sba(history: np.ndarray, horizon: int, alpha: float = 0.1) -> np.ndarray:
    out = np.zeros(history.shape[0])
    for i, row in enumerate(history):
        values = row[~np.isnan(row)]
        sale_days = np.flatnonzero(values > 0)
        if sale_days.size == 0:
            continue
        size, interval = values[sale_days[0]], float(sale_days[0] + 1)
        for prev, day in zip(sale_days[:-1], sale_days[1:]):
            size += alpha * (values[day] - size)
            interval += alpha * ((day - prev) - interval)
        out[i] = (1 - alpha / 2) * size / interval
    return np.repeat(out[:, None], horizon, axis=1)


def tsb(history: np.ndarray, horizon: int, alpha: float = 0.1, beta: float = 0.1) -> np.ndarray:
    out = np.zeros(history.shape[0])
    for i, row in enumerate(history):
        values = row[~np.isnan(row)]
        sold = values > 0
        if not sold.any():
            continue
        prob, size = sold.mean(), values[sold].mean()        # start from the overall averages
        for value, did_sell in zip(values, sold):
            prob += beta * (float(did_sell) - prob)
            if did_sell:
                size += alpha * (value - size)
        out[i] = prob * size
    return np.repeat(out[:, None], horizon, axis=1)
