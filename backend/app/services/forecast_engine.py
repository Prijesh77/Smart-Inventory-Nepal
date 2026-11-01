"""Bridge between the database and the ml/ forecasting code.

Rebuilds, from the database, the same item x day table that the models were
trained on (ml/features/build.py), then produces daily forecasts.

Days after the last sales day are added as "future" rows:
  - weekday and month come from the date, Nepali festival features from
    ml/calendar/festivals.py, and closures from calendar_days (open if not listed);
  - the price is assumed to stay at the last known price (no planned
    price changes are known to the app). Both assumptions are recorded on
    every forecast run.
"""

from __future__ import annotations

import json
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
from app.db.tenancy import current_shop_id
from app.models import CalendarDay, Category, DailySales, Product
from ml.calendar.festivals import FESTIVAL_FEATURES, festival_features
from ml.features.build import FEATURES, MIN_HISTORY_DAYS, Panel, build_rows, make_panel
from ml.models.baselines import moving_average
from ml.models.forest import predict

# One model per shop, trained on that shop's own sales by backend/scripts/train_model.py (or seed.py);
# never on M5 data.
MODEL_DIR = PROJECT_ROOT / "models"
MODELS = {
    "random_forest_v1": "Random Forest (trained on this shop's sales)",
    "moving_avg_28": "28-day moving average (baseline)",
}
ASSUMPTIONS = [
    "Prices after the last sales day are assumed unchanged.",
    "Festival dates come from the Nepali festival calendar (ml/calendar/nepal_festivals.json).",
    "Forecasts are of recorded sales, which can be lower than true demand during stockouts.",
]


# Least sales history before a forecast's first day. The forest's features look back 91 days; the moving
# average works from two weeks, so a new shop gets forecasts (and reorder suggestions) early.
MIN_MA_HISTORY_DAYS = 14


def min_history_days(model_name: str) -> int:
    return MIN_HISTORY_DAYS if model_name == "random_forest_v1" else MIN_MA_HISTORY_DAYS


class ForecastUnavailable(Exception):
    pass


def model_file(shop_id: int) -> Path:
    return MODEL_DIR / f"shop_{shop_id}_random_forest.joblib"


def model_is_current(path: Path) -> bool:
    """True if the saved forest was trained with today's feature list (e.g. not before festival features)."""
    meta = path.with_suffix(".json")
    if not path.exists() or not meta.exists():
        return False
    return json.loads(meta.read_text(encoding="utf-8")).get("features") == FEATURES


def load_rf_model(path: Path):
    if not path.exists():
        raise ForecastUnavailable(
            "This shop's Random Forest has not been trained yet. Use the 28-day moving average, or train it "
            "with: python backend/scripts/train_model.py")
    if not model_is_current(path):
        raise ForecastUnavailable("This shop's Random Forest was trained before the Nepali festival features "
                                  "were added; retrain it (Forecasting page, 'Retrain model').")
    return _load_file(path, path.stat().st_mtime)


@lru_cache(maxsize=32)
def _load_file(path: Path, _modified: float):
    """Cached per file and modification time, so a retrained model is picked up without a restart."""
    return joblib.load(path)


def m5_wday(day: date) -> int:
    """M5 weekday numbering used in training: Saturday = 1 ... Friday = 7."""
    return (day.weekday() + 2) % 7 + 1


@dataclass
class ForecastContext:
    shop_id: int
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
        # Open unless the calendar says closed (e.g. Vijaya Dashami in the demo shop).
        "is_store_open": [stored[d].is_store_open if d in stored else True for d in all_days],
    })
    festival = festival_features(all_days)
    for column in FESTIVAL_FEATURES:
        cal[column] = festival[column].to_numpy()
    daily = daily.merge(cal, on="sales_date", how="left")
    daily["is_available"] = daily["is_available"] & daily["is_store_open"]
    daily["d_num"] = [(d - first).days + 1 for d in daily["sales_date"]]

    panel = make_panel(daily, last_day=len(all_days))
    ids = daily.drop_duplicates("item_id").set_index("item_id")["product_id"]
    return ForecastContext(shop_id=current_shop_id(db), panel=panel, product_ids=ids.reindex(panel.item_ids).to_numpy(),
                           first_date=first, last_sales_date=last, open_day=cal["is_store_open"].to_numpy(bool))


def forecast_matrix(ctx: ForecastContext, model_name: str, origin: date, horizon: int) -> np.ndarray:
    """Daily forecasts (items x horizon) from `origin`, using only sales before `origin`."""
    origin_d = ctx.d_num(origin)
    needed = min_history_days(model_name)
    if origin_d - 1 < needed:
        raise ForecastUnavailable(f"Need at least {needed} days of sales history before {origin}; "
                                  f"there are {max(origin_d - 1, 0)}")
    if origin > ctx.last_sales_date + timedelta(days=1):
        raise ForecastUnavailable(f"Origin {origin} is after the day following the last sales day")
    if model_name == "moving_avg_28":
        values = moving_average(ctx.panel.sales[:, : origin_d - 1], horizon, 28)
    elif model_name == "random_forest_v1":
        rows = build_rows(ctx.panel, [origin_d], horizon)
        values = predict(load_rf_model(model_file(ctx.shop_id)), rows).reshape(len(ctx.panel.item_ids), horizon)
    else:
        raise ForecastUnavailable(f"Unknown model '{model_name}'")
    closed = ~ctx.open_day[origin_d - 1: origin_d - 1 + horizon]
    values = np.where(closed[None, :], 0.0, values)
    return np.clip(np.nan_to_num(values), 0, None)
