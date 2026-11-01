"""Train the Random Forest on the shop's own sales in the database (no M5 data).

Steps
  1. Check: hold back the last 28 days, train on everything before them, and
     score the forest and the 28-day moving average on the held-back days.
     The scores are saved as model_evaluations (period "test") for the
     Forecasting page, so the shop can see whether the forest is worth using.
  2. Final model: train again on all days and save it to the shop's model file
     (models/shop_<id>_random_forest.joblib).

Training rows come from forecast origins every 7 days, each with h = 1..28,
using the same leakage-safe features as the forecasts (ml/features/build.py).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError, ConflictError
from app.db.tenancy import current_shop_id, shop_session
from app.models import DailySales, ModelEvaluation, Product
from app.models.enums import EvaluationPeriod
from app.services.forecast_engine import ForecastUnavailable, load_context, model_file
from app.services.forecasting import choose_model, holdout_wape, last_sales_date
from ml.evaluation.metrics import summarize
from ml.features.build import MIN_HISTORY_DAYS, build_rows
from ml.models.baselines import moving_average
from ml.models.forest import fit_forest, predict, save_model, training_rows

HOLDOUT_DAYS = 28
ORIGIN_STEP_DAYS = 7
MIN_TRAINING_ORIGINS = 8
SCORE_HORIZONS = (7, 14, 28)
RF_VERSION = "shop-v1"
logger = logging.getLogger("app.training")


def _origins(first: int, last: int) -> list[int]:
    return list(range(first, last + 1, ORIGIN_STEP_DAYS))


def _fit(panel, last_target_day: int):
    origins = _origins(MIN_HISTORY_DAYS + 1, last_target_day - HOLDOUT_DAYS + 1)
    rows = training_rows(build_rows(panel, origins, HOLDOUT_DAYS), last_target_day)
    return fit_forest(rows), len(origins), len(rows)


def train_shop_model(db: Session, path: Path | None = None) -> dict:
    """Score, then train and save the current shop's forest. Returns a summary for printing."""
    ctx = load_context(db, through=last_sales_date(db))
    path = path or model_file(ctx.shop_id)
    panel, n_days = ctx.panel, ctx.panel.sales.shape[1]
    holdout_origin = n_days - HOLDOUT_DAYS + 1
    needed = MIN_HISTORY_DAYS + ORIGIN_STEP_DAYS * MIN_TRAINING_ORIGINS + 2 * HOLDOUT_DAYS
    if n_days < needed:
        raise ForecastUnavailable(f"Training needs at least {needed} days of sales; the shop has {n_days}")

    # 1. Check on the held-back last 28 days.
    check_model, _, _ = _fit(panel, holdout_origin - 1)
    holdout = build_rows(panel, [holdout_origin], HOLDOUT_DAYS)
    rf = predict(check_model, holdout).reshape(len(panel.item_ids), HOLDOUT_DAYS)
    ma = moving_average(panel.sales[:, : holdout_origin - 1], HOLDOUT_DAYS, 28)
    actual = panel.sales[:, holdout_origin - 1:]
    classes = dict(db.execute(select(Product.sku, Product.demand_class)).all())
    item_class = np.array([classes.get(sku) or "unknown" for sku in panel.item_ids])

    db.execute(delete(ModelEvaluation).where(ModelEvaluation.model_name.in_(["random_forest_v1", "moving_avg_28"])))
    scores = []
    for model_name, version, values in [("random_forest_v1", RF_VERSION, rf), ("moving_avg_28", "baseline", ma)]:
        for horizon in SCORE_HORIZONS:
            for demand_class in ["all", *sorted(set(item_class))]:
                keep = slice(None) if demand_class == "all" else item_class == demand_class
                s = summarize(actual[keep, :horizon], values[keep, :horizon])
                if s["n"] == 0:
                    continue
                scores.append(ModelEvaluation(
                    model_name=model_name, model_version=version, period=EvaluationPeriod.TEST,
                    horizon_days=horizon, demand_class=demand_class, n_observations=s["n"],
                    **{k: _num(s[k]) for k in ("mae", "rmse", "wape", "bias_pct")}))
    db.add_all(scores)

    # 2. Final model on all the data.
    model, n_origins, n_rows = _fit(panel, n_days)
    first_day, last_day = ctx.first_date, ctx.date_of(n_days)
    save_model(model, path, {"trained_on": "this shop's sales in the database",
                             "history": [str(first_day), str(last_day)], "origins": n_origins,
                             "training_rows": n_rows, "items": int(len(panel.item_ids))})
    db.commit()

    wape = {m: next(float(e.wape) for e in scores if e.model_name == m and e.horizon_days == 28
                    and e.demand_class == "all") for m in ("random_forest_v1", "moving_avg_28")}
    return {"items": int(len(panel.item_ids)), "history_days": n_days, "training_rows": n_rows,
            "holdout": f"{ctx.date_of(holdout_origin)} .. {last_day}",
            "wape_28d_random_forest": round(wape["random_forest_v1"], 3),
            "wape_28d_moving_avg_28": round(wape["moving_avg_28"], 3),
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "file": str(path)}


MIN_TRAINING_DAYS = MIN_HISTORY_DAYS + ORIGIN_STEP_DAYS * MIN_TRAINING_ORIGINS + 2 * HOLDOUT_DAYS   # about 7 months
_training: dict[int, dict] = {}       # shop id -> {"state": "running" | "failed", "message": ...} (this process)


def history_days(db: Session) -> int:
    first, last = db.execute(select(func.min(DailySales.sales_date), func.max(DailySales.sales_date))).one()
    return (last - first).days + 1 if first else 0


def model_status(db: Session) -> dict:
    """What the Forecasting page shows about the shop's own Random Forest."""
    shop_id = current_shop_id(db)
    path = model_file(shop_id)
    trained_at = None
    if path.exists() and path.with_suffix(".json").exists():
        trained_at = json.loads(path.with_suffix(".json").read_text(encoding="utf-8")).get("created_at")
    days = history_days(db)
    model, reason = choose_model(db, "auto")
    job = _training.get(shop_id, {})
    return {"trained": path.exists(), "trained_at": trained_at, "history_days": days,
            "needed_days": MIN_TRAINING_DAYS, "can_train": days >= MIN_TRAINING_DAYS,
            "training": job.get("state") == "running", "last_error": job.get("message"),
            "holdout_wape": holdout_wape(db), "auto_uses": model, "auto_reason": reason}


def start_training(db: Session) -> int:
    """Check that training can start now; mark it running. Returns the shop id for the background job."""
    shop_id = current_shop_id(db)
    if _training.get(shop_id, {}).get("state") == "running":
        raise ConflictError("Training is already running for this shop")
    days = history_days(db)
    if days < MIN_TRAINING_DAYS:
        raise ConflictError(f"Training needs about {MIN_TRAINING_DAYS} days (7 months) of sales; this shop has "
                            f"{days}. Until then the 28-day moving average is used.")
    _training[shop_id] = {"state": "running"}
    return shop_id


def train_in_background(session_factory: sessionmaker[Session], shop_id: int) -> None:
    with shop_session(session_factory, shop_id) as db:
        try:
            train_shop_model(db)
            _training.pop(shop_id, None)
        except (ForecastUnavailable, AppError) as exc:
            db.rollback()
            _training[shop_id] = {"state": "failed", "message": str(exc)}
        except Exception as exc:   # recorded for the page instead of being lost
            logger.exception("Training for shop %s failed", shop_id)
            db.rollback()
            _training[shop_id] = {"state": "failed", "message": f"Unexpected error: {type(exc).__name__}"}


def _num(value: float):
    return None if value is None or np.isnan(value) else round(float(value), 4)
