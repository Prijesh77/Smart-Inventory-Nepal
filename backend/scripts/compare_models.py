"""Compare forecasting methods on the demo shops with a rolling-origin backtest.

    .venv\\Scripts\\python.exe backend\\scripts\\compare_models.py [--windows 4]

For each of the last N non-overlapping 28-day windows, every method is given only the sales before the window
(machine-learning models are retrained each time) and asked for the next 28 days. Scores are pooled over all
windows, so one unusual month does not decide the result. Reads the demo SQLite database; writes nothing to it.
The report is written to docs/31_model_comparison.md.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'data' / 'demo' / 'demo.db').as_posix()}"
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

import numpy as np  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.db.tenancy import SHOP_KEY  # noqa: E402
from app.models import DailySales, Product, Shop  # noqa: E402
from app.services.forecast_engine import load_context  # noqa: E402
from ml import config  # noqa: E402
from ml.features.build import FEATURES, MIN_HISTORY_DAYS, build_rows  # noqa: E402
from ml.models.baselines import moving_average  # noqa: E402
from ml.models.forest import RF_PARAMS, training_rows  # noqa: E402
from ml.models.intermittent import sba, tsb  # noqa: E402

HORIZON = 28
STEP = 7
REPORT = ROOT / "docs" / "31_model_comparison.md"

ML_MODELS = {
    "Random Forest (current)": lambda: RandomForestRegressor(**RF_PARAMS),
    "Random Forest (earlier settings)": lambda: RandomForestRegressor(
        n_estimators=100, min_samples_leaf=50, max_features=0.5, max_samples=0.3, n_jobs=-1, random_state=config.SEED),
    "Gradient boosting (Poisson)": lambda: HistGradientBoostingRegressor(
        loss="poisson", learning_rate=0.05, max_iter=300, max_leaf_nodes=31, min_samples_leaf=20,
        l2_regularization=1.0, random_state=config.SEED),
}


def train_rows(panel, origin: int):
    """Training rows from weekly origins whose 28-day windows end before `origin` (no look-ahead)."""
    last_target = origin - 1
    origins = list(range(MIN_HISTORY_DAYS + 1, last_target - HORIZON + 2, STEP))
    return training_rows(build_rows(panel, origins, HORIZON), last_target)


def forecasts_for_window(panel, origin: int) -> dict[str, np.ndarray]:
    history = panel.sales[:, : origin - 1]
    n_items = len(panel.item_ids)
    out = {
        "28-day moving average": moving_average(history, HORIZON, 28),
        "SBA (Croston, for intermittent items)": sba(history, HORIZON),
        "TSB (for intermittent items)": tsb(history, HORIZON),
    }
    rows = train_rows(panel, origin)
    test = build_rows(panel, [origin], HORIZON)
    for name, make in ML_MODELS.items():
        model = make()
        model.fit(rows[FEATURES].to_numpy(), rows["target"].to_numpy())
        out[name] = np.clip(model.predict(test[FEATURES].to_numpy()).reshape(n_items, HORIZON), 0, None)
    out["Forest + moving average (average)"] = (out["Random Forest (current)"] + out["28-day moving average"]) / 2
    out["Boosting + moving average (average)"] = (out["Gradient boosting (Poisson)"] + out["28-day moving average"]) / 2
    return out


def scores(actual: np.ndarray, forecast: np.ndarray) -> tuple[float, float, float]:
    """(absolute error, actual units, signed error) over available days only."""
    ok = ~np.isnan(actual)
    err = forecast[ok] - actual[ok]
    return float(np.abs(err).sum()), float(actual[ok].sum()), float(err.sum())


def run_shop(db: Session, windows: int) -> tuple[dict, dict, int, list[str]]:
    last = db.scalar(select(DailySales.sales_date).order_by(DailySales.sales_date.desc()).limit(1))
    ctx = load_context(db, through=last)
    panel, n_days = ctx.panel, ctx.panel.sales.shape[1]
    classes_by_sku = dict(db.execute(select(Product.sku, Product.demand_class)).all())
    item_class = np.array([classes_by_sku.get(sku) or "unknown" for sku in panel.item_ids])
    origins = [n_days - HORIZON * k + 1 for k in range(windows, 0, -1)]
    totals: dict[str, dict[str, list[float]]] = {}
    for origin in origins:
        actual = panel.sales[:, origin - 1: origin - 1 + HORIZON]
        for model, values in forecasts_for_window(panel, origin).items():
            for cls in ["all", *sorted(set(item_class))]:
                keep = slice(None) if cls == "all" else item_class == cls
                e, a, b = scores(actual[keep], values[keep])
                t = totals.setdefault(model, {}).setdefault(cls, [0.0, 0.0, 0.0])
                t[0] += e; t[1] += a; t[2] += b
    counts = {cls: int((item_class == cls).sum()) for cls in set(item_class)}
    labels = [str(ctx.date_of(o)) for o in origins]
    return totals, counts, n_days, labels


def table(totals: dict, classes: list[str], baseline: str) -> list[str]:
    head = "| Method | All products | " + " | ".join(c.capitalize() for c in classes) + " | Bias (all) |"
    lines = [head, "|" + "---|" * (len(classes) + 3)]
    for model, by_cls in sorted(totals.items(), key=lambda kv: kv[1]["all"][0] / kv[1]["all"][1]):
        e, a, b = by_cls["all"]
        cells = [f"**{e / a:.1%}**" if model == min(totals, key=lambda m: totals[m]['all'][0] / totals[m]['all'][1]) else f"{e / a:.1%}"]
        for cls in classes:
            ce, ca, _ = by_cls.get(cls, [0, 0, 0])
            best = min(totals, key=lambda m: totals[m].get(cls, [np.inf, 1])[0] / max(totals[m].get(cls, [0, 1])[1], 1e-9))
            cell = f"{ce / ca:.1%}" if ca else "-"
            cells.append(f"**{cell}**" if model == best else cell)
        lines.append(f"| {model} | " + " | ".join(cells) + f" | {b / a:+.1%} |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--windows", type=int, default=4, help="number of 28-day test windows (default 4)")
    args = parser.parse_args()
    started = time.time()
    engine = get_engine()
    with Session(engine) as plain:
        shops = plain.execute(select(Shop.id, Shop.name)).all()
    report = ["# Forecasting model comparison", "",
              f"Rolling-origin backtest on the demo shops (synthetic data): the last {args.windows} non-overlapping "
              f"{HORIZON}-day windows of each shop. Each method only sees sales before its window, and the "
              "machine-learning models are retrained for every window. Scores are WAPE (total absolute error as a "
              "share of units sold; lower is better), pooled over all windows. Bold marks the best method in each "
              "column. Bias is total forecast minus total actual, as a share of actual (negative = under-forecast).", "",
              "Generated by `backend/scripts/compare_models.py`.", ""]
    for shop_id, name in shops:
        with Session(engine, info={SHOP_KEY: shop_id}) as db:
            span = db.execute(select(DailySales.sales_date).order_by(DailySales.sales_date)).scalars().all()
            if not span or (span[-1] - span[0]).days + 1 < MIN_HISTORY_DAYS + HORIZON * (args.windows + 2):
                print(f"shop {shop_id} skipped: not enough history for {args.windows} test windows")
                continue
            totals, counts, n_days, labels = run_shop(db, args.windows)
        classes = sorted(c for c in counts if c != "unknown")
        report += [f"## {name}", "",
                   f"{n_days} days of history; test windows start {', '.join(labels)}. Products per pattern: "
                   + ", ".join(f"{c} {counts[c]}" for c in classes) + ".", "",
                   *table(totals, classes, "28-day moving average"), ""]
        print(f"shop {shop_id} done ({time.time() - started:.0f}s)")
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
