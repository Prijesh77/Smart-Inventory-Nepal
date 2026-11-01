"""Train a Random Forest and compare it with the baselines on the same
rolling origins and metrics.

Two periods:
  validation  fit on targets up to the end of training; evaluate on the
              6 validation origins. Used for model development.
  test        fit on targets up to the end of validation; evaluate on the
              13 test-year origins. Run once, after the model choice is
              locked; nothing is tuned on these results.

The model is fitted once per period. At each evaluation origin it receives
features built from all sales before that origin, but it is not refitted.
This is slightly harder for the forest than for the moving averages, which
always use the latest days.

    python -m ml.experiments.run_random_forest --period validation
    python -m ml.experiments.run_random_forest --period test
"""

from __future__ import annotations

import argparse
import time

import pandas as pd

from ml import config
from ml.data.inspect_m5 import Report
from ml.evaluation.backtest import best_model_share, build_sales_matrix, evaluate, rolling_origins, run_backtest
from ml.features.build import MIN_HISTORY_DAYS, build_rows, make_panel
from ml.models.baselines import BASELINES
from ml.models.forest import RF_PARAMS, feature_importance, fit_forest, predict, save_model, training_rows

MODEL_NAME = "random_forest_v1"
COMPARE = ["moving_avg_7", "moving_avg_28", "seasonal_naive_7", MODEL_NAME]
CLASS_ORDER = ["all", "smooth", "erratic", "intermittent", "lumpy"]

PERIODS = {
    "validation": {
        "fit_end": config.TRAIN_END,
        "eval_start": config.VALIDATION_START,
        "eval_end": config.TEST_START - 1,
        "model_file": MODEL_NAME,
    },
    "test": {
        "fit_end": config.TEST_START - 1,
        "eval_start": config.TEST_START,
        "eval_end": config.LAST_DAY,
        "model_file": f"{MODEL_NAME}_final",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Random Forest vs baselines.")
    parser.add_argument("--period", choices=list(PERIODS), default="validation")
    args = parser.parse_args()
    period = PERIODS[args.period]

    report = Report()
    daily = pd.read_parquet(config.PROCESSED_DIR / "sample_daily.parquet")
    classes = daily[["item_id", "demand_class"]].drop_duplicates().astype(str).set_index("item_id")["demand_class"]
    panel = make_panel(daily, config.LAST_DAY)

    # ---- fitting rows: every origin whose 28-day window ends inside the fit period
    fit_end = period["fit_end"]
    train_origins = rolling_origins(MIN_HISTORY_DAYS + 1, fit_end, config.MAX_HORIZON, config.TRAIN_ORIGIN_STEP)
    train = training_rows(build_rows(panel, train_origins, config.MAX_HORIZON), fit_end)
    report.section(f"Training ({args.period} run)")
    report.add(f"Origins: {len(train_origins)} (d_{train_origins[0]} .. d_{train_origins[-1]}, every {config.TRAIN_ORIGIN_STEP} days)")
    report.add(f"Training rows (item x origin x horizon with known target): {len(train):,}")
    report.add(f"Latest target day used for fitting: d_{int(train['d_num'].max())} (fit period ends d_{fit_end})")
    report.add(f"Parameters: {RF_PARAMS}")

    start = time.perf_counter()
    model = fit_forest(train)
    report.add(f"Fit time: {time.perf_counter() - start:.0f} s")

    # ---- evaluation origins: same spacing as the baseline experiment
    eval_origins = rolling_origins(period["eval_start"], period["eval_end"], config.MAX_HORIZON, config.BACKTEST_STEP)
    rows = build_rows(panel, eval_origins, config.MAX_HORIZON)
    rf_results = pd.DataFrame({
        "model": MODEL_NAME, "origin": rows["origin"], "item_id": rows["item_id"], "h": rows["h"],
        "d_num": rows["d_num"], "actual": rows["target"], "forecast": predict(model, rows),
    })
    matrix = build_sales_matrix(daily, config.LAST_DAY)
    baselines = {name: BASELINES[name] for name in COMPARE if name in BASELINES}
    results = pd.concat([run_backtest(matrix, baselines, eval_origins, config.MAX_HORIZON), rf_results], ignore_index=True)
    scores = evaluate(results, classes, config.FORECAST_HORIZONS)
    report.add(f"Evaluation origins: {['d_' + str(o) for o in eval_origins]}")

    for horizon in config.FORECAST_HORIZONS:
        report.section(f"{args.period.capitalize()}, horizon 1-{horizon} days")
        part = scores[scores["horizon"] == horizon]
        for metric, fmt in [("wape", "{:.1%}"), ("mae", "{:.3f}"), ("rmse", "{:.3f}"), ("bias_pct", "{:+.1%}")]:
            table = part.pivot(index="model", columns="demand_class", values=metric).reindex(COMPARE)[CLASS_ORDER]
            report.add(f"{metric.upper()}")
            report.add(table.map(fmt.format).to_string())
            report.add()

    report.section("Share of items where each model has the lowest MAE (1-28 days)")
    report.add(best_model_share(results, config.MAX_HORIZON).map("{:.1%}".format).to_string())

    report.section("Lead-time view: error on 7-day TOTALS per item (days 1-7 summed)")
    week = results[(results["h"] <= 7) & results["actual"].notna()]
    totals = week.groupby(["model", "origin", "item_id"])[["actual", "forecast"]].sum().reset_index()
    totals = totals.assign(demand_class=totals["item_id"].map(classes), abs_err=(totals["forecast"] - totals["actual"]).abs())
    weekly_wape = (
        totals.groupby(["model", "demand_class"])[["abs_err", "actual"]].sum()
        .pipe(lambda t: t["abs_err"] / t["actual"]).unstack()
    )
    weekly_wape["all"] = totals.groupby("model")["abs_err"].sum() / totals.groupby("model")["actual"].sum()
    report.add(weekly_wape.reindex(COMPARE)[CLASS_ORDER].map("{:.1%}".format).to_string())

    report.section("Per-origin WAPE and bias (1-28 days, all items)")
    observed = results[results["actual"].notna()]
    per_origin = observed.groupby(["origin", "model"]).apply(
        lambda t: pd.Series({
            "wape": (t["forecast"] - t["actual"]).abs().sum() / t["actual"].sum(),
            "bias": (t["forecast"] - t["actual"]).sum() / t["actual"].sum(),
        }),
        include_groups=False,
    )
    for metric in ["wape", "bias"]:
        report.add(metric.upper())
        report.add(per_origin[metric].unstack().reindex(columns=COMPARE).map("{:.1%}".format).to_string())
        report.add()
    wape_by_origin = per_origin["wape"].unstack()
    wins = int((wape_by_origin[MODEL_NAME] < wape_by_origin["moving_avg_28"]).sum())
    report.add(f"{MODEL_NAME} beats moving_avg_28 at {wins} of {len(wape_by_origin)} origins")

    report.section("Feature importance (impurity-based, rough guide)")
    report.add(feature_importance(model).map("{:.3f}".format).to_string())

    all_28 = scores[(scores["horizon"] == config.MAX_HORIZON) & (scores["demand_class"] == "all")].set_index("model")
    save_model(model, config.MODELS_DIR / f"{period['model_file']}.joblib", {
        "model_name": MODEL_NAME,
        "store": config.STORE_ID,
        "train_origins": [train_origins[0], train_origins[-1], config.TRAIN_ORIGIN_STEP],
        "last_target_day": fit_end,
        "n_training_rows": len(train),
        "evaluation_period": args.period,
        "evaluation_origins": eval_origins,
        "evaluation_28d_all": all_28.loc[MODEL_NAME, ["wape", "mae", "rmse", "bias_pct"]].to_dict(),
    })

    out = config.RESULTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    prefix = f"random_forest_{args.period}"
    scores.to_csv(out / f"{prefix}_scores.csv", index=False)
    results.to_parquet(out / f"{prefix}_forecasts.parquet", index=False)
    report.save(out / f"{prefix}_report.txt")
    print(f"\nSaved model to {config.MODELS_DIR} and results to {out}")


if __name__ == "__main__":
    main()
