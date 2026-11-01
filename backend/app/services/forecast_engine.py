"""Bridge between the database and the ml/ forecasting code.

Rebuilds, from the database, the same item x day table that the models were
trained on (ml/features/build.py), then produces daily forecasts.

Days after the last sales day are added as "future" rows:
  - calendar facts (weekday, month, SNAP, events, closures) come from
    calendar_days when present, otherwise weekday/month are derived from the
    date and SNAP/events are assumed absent;
  - the price is assumed to stay at the last known price (no planned
    price changes are known to the app). Both assumptions are recorded on
    every forecast run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.models import CalendarDay, Category, DailySales, Product
from ml.features.build import MIN_HISTORY_DAYS, Panel, build_rows, make_panel
from ml.models.baselines import moving_average
from ml.models.forest import predict

RF_MODEL_FILE = PROJECT_ROOT / "models" / "random_forest_v1_final.joblib"
MODELS = {
    "random_forest_v1": "Random Forest (fitted on train + validation, Phase 3)",
    "moving_avg_28": "28-day moving average (baseline)",
}
ASSUMPTIONS = [
    "Prices after the last sales day are assumed unchanged.",
    "Calendar facts after the stored calendar are derived from the date (no SNAP or events).",
    "Forecasts are of recorded sales, which can be lower than true demand during stockouts.",
]


class ForecastUnavailable(Exception):
    pass


@lru_cache
def load_rf_model(path: Path = RF_MODEL_FILE):
    if not path.exists():
        raise ForecastUnavailable(
            f"Model file {path.name} not found. Run: python -m ml.experiments.run_random_forest --period test")
    return joblib.load(path)


def m5_wday(day: date) -> int:
    """M5 weekday numbering used in training: Saturday = 1 ... Friday = 7."""
    return (day.weekday() + 2) % 7 + 1


@dataclass
class ForecastContext:
    panel: Panel
    product_ids: np.ndarray          # aligned with panel.item_ids
    first_date: date
    last_sales_date: date
    open_day: np.ndarray              # per d_num - 1

    def d_num(self, day: date) -> int:
        return (day - self.first_date).days + 1

    def date_of(self, d_num: int) -> date:
        return self.first_date + timedelta(days=d_num - 1)


def load_context(db: Session, through: date) -> ForecastContext:
    """Item x day data for all active products with sales, extended with future rows up to `through`."""
    rows = db.execute(
        select(Product.id.label("product_id"), Product.sku.label("item_id"), Product.department.label("dept_id"),
               Category.code.label("cat_id"), DailySales.sales_date, DailySales.units.label("sales"),
               DailySales.unit_price.label("sell_price"), DailySales.is_available)
        .join(Product, Product.id == DailySales.product_id)
        .join(Category, Category.id == Product.category_id)
        .where(Product.is_active.is_(True))
    ).all()
    if not rows:
        raise ForecastUnavailable("No sales history in the database")
    daily = pd.DataFrame(rows, columns=["product_id", "item_id", "dept_id", "cat_id", "sales_date", "sales",
                                        "sell_price", "is_available"])
    daily["sell_price"] = daily["sell_price"].astype(float)
    daily["sales"] = daily["sales"].astype(float)
    first, last = daily["sales_date"].min(), daily["sales_date"].max()
    through = max(through, last)

    # Future rows: one per product per day after the data, at the last known price.
    if through > last:
        latest = daily.sort_values("sales_date").groupby("product_id").tail(1)
        future_days = [last + timedelta(days=k) for k in range(1, (through - last).days + 1)]
        future = latest.loc[latest.index.repeat(len(future_days))].copy()
        future["sales_date"] = future_days * len(latest)
        future["sales"] = np.nan
        future["is_available"] = True
        daily = pd.concat([daily, future], ignore_index=True)

    stored = {c.day: c for c in db.scalars(select(CalendarDay).where(CalendarDay.day.between(first, through)))}
    all_days = [first + timedelta(days=k) for k in range((through - first).days + 1)]
    cal = pd.DataFrame({
        "sales_date": all_days,
        "wday": [m5_wday(d) for d in all_days],
        "month": [d.month for d in all_days],
        "snap": [int(stored[d].snap) if d in stored else 0 for d in all_days],
        "event_type_1": [stored[d].event_type if d in stored else None for d in all_days],
        "is_store_open": [stored[d].is_store_open if d in stored else not (d.month == 12 and d.day == 25)
                          for d in all_days],
    })
    daily = daily.merge(cal, on="sales_date", how="left")
    daily["is_available"] = daily["is_available"] & daily["is_store_open"]
    daily["d_num"] = [(d - first).days + 1 for d in daily["sales_date"]]

    panel = make_panel(daily, last_day=len(all_days))
    ids = daily.drop_duplicates("item_id").set_index("item_id")["product_id"]
    return ForecastContext(panel=panel, product_ids=ids.reindex(panel.item_ids).to_numpy(),
                           first_date=first, last_sales_date=last, open_day=cal["is_store_open"].to_numpy(bool))


def forecast_matrix(ctx: ForecastContext, model_name: str, origin: date, horizon: int) -> np.ndarray:
    """Daily forecasts (items x horizon) from `origin`, using only sales before `origin`."""
    origin_d = ctx.d_num(origin)
    if origin_d - 1 < MIN_HISTORY_DAYS:
        raise ForecastUnavailable(f"Need at least {MIN_HISTORY_DAYS} days of history before {origin}")
    if origin > ctx.last_sales_date + timedelta(days=1):
        raise ForecastUnavailable(f"Origin {origin} is after the day following the last sales day")
    if model_name == "moving_avg_28":
        values = moving_average(ctx.panel.sales[:, : origin_d - 1], horizon, 28)
    elif model_name == "random_forest_v1":
        rows = build_rows(ctx.panel, [origin_d], horizon)
        values = predict(load_rf_model(), rows).reshape(len(ctx.panel.item_ids), horizon)
    else:
        raise ForecastUnavailable(f"Unknown model '{model_name}'")
    closed = ~ctx.open_day[origin_d - 1: origin_d - 1 + horizon]
    values = np.where(closed[None, :], 0.0, values)
    return np.clip(np.nan_to_num(values), 0, None)
