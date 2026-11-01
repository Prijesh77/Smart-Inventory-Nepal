"""Evaluate baseline forecasters on the validation period with rolling origins.

The test period is NOT used here; it is kept for the final comparison.

    python -m ml.experiments.run_baselines
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml import config
from ml.data.inspect_m5 import Report
from ml.evaluation.backtest import best_model_share, build_sales_matrix, evaluate, rolling_origins, run_backtest
from ml.models.baselines import BASELINES

CLASS_ORDER = ["all", "smooth", "erratic", "intermittent", "lumpy"]


def metric_table(scores: pd.DataFrame, metric: str, horizon: int) -> pd.DataFrame:
    """Models as rows, demand classes as columns, for one metric and horizon."""
    part = scores[scores["horizon"] == horizon]
    table = part.pivot(index="model", columns="demand_class", values=metric)
    return table[[c for c in CLASS_ORDER if c in table.columns]].reindex(list(BASELINES))


def main() -> None:
    report = Report()
    daily = pd.read_parquet(config.PROCESSED_DIR / "sample_daily.parquet")
    classes = (
        daily[["item_id", "demand_class"]].drop_duplicates()
        .astype(str).set_index("item_id")["demand_class"]
    )
    matrix = build_sales_matrix(daily, config.LAST_DAY)
    origins = rolling_origins(config.VALIDATION_START, config.TEST_START - 1, config.MAX_HORIZON, config.BACKTEST_STEP)

    report.section("Setup")
    report.add(f"Items: {len(matrix)}; models: {list(BASELINES)}")
    report.add(f"Origins (validation period only): {['d_' + str(o) for o in origins]}")
    report.add(f"Horizon per origin: {config.MAX_HORIZON} days; metrics for days 1..{list(config.FORECAST_HORIZONS)}")

    results = run_backtest(matrix, BASELINES, origins, config.MAX_HORIZON)
    scores = evaluate(results, classes, config.FORECAST_HORIZONS)

    for horizon in config.FORECAST_HORIZONS:
        report.section(f"Horizon 1-{horizon} days")
        for metric, fmt in [("wape", "{:.1%}"), ("mae", "{:.3f}"), ("rmse", "{:.3f}"), ("bias_pct", "{:+.1%}")]:
            table = metric_table(scores, metric, horizon)
            report.add(f"{metric.upper()} (rows: model, columns: demand class)")
            report.add(table.map(fmt.format).to_string())
            report.add()

    report.section("Share of items where each model has the lowest MAE (1-28 days, excluding zero_reference)")
    report.add(best_model_share(results, config.MAX_HORIZON, exclude=["zero_reference"]).map("{:.1%}".format).to_string())

    out_dir = config.RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    scores.to_csv(out_dir / "baselines_validation_scores.csv", index=False)
    results.to_parquet(out_dir / "baselines_validation_forecasts.parquet", index=False)
    report.save(out_dir / "baselines_validation_report.txt")
    print(f"\nSaved results to {out_dir}")


if __name__ == "__main__":
    main()
