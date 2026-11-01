"""Sensitivity analysis for the inventory simulation (all results SIMULATED).

Each scenario changes ONE assumption from the base case and reruns all
policies at all service levels. For every scenario we report each policy's
highest reachable fill rate and the cost difference at a matched fill rate.
The base case also gets a bootstrap confidence interval over items.

    python -m ml.experiments.run_sensitivity
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ml import config  # noqa: E402
from ml.data.inspect_m5 import Report  # noqa: E402
from ml.evaluation.inventory_compare import bootstrap_matched, matched_difference  # noqa: E402
from ml.experiments.run_simulation import POLICIES, SERVICE_LEVELS, prepare, run_policy, summarize  # noqa: E402
from ml.inventory.simulation import CostSettings  # noqa: E402
from ml.inventory.synthetic import SyntheticConfig, generate  # noqa: E402

COMPARISONS = [("engine_rf", "baseline_demand_sd"), ("engine_rf", "engine_ma28"), ("engine_ma28", "baseline_demand_sd")]
N_BOOT = 1000


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    synthetic_seed: int = config.SEED
    uniform_lead_time: int | None = None
    uncertain_lead_time: bool = False
    costs: CostSettings = field(default_factory=CostSettings)


SCENARIOS = [
    Scenario("base", "Base case: fixed supplier lead times, $10/order, 25%/yr holding"),
    Scenario("lead_time_uncertain", "Real lead times vary (supplier SD 0.5-3 days); policies plan with the mean",
             uncertain_lead_time=True),
    Scenario("lead_time_all_3d", "Every item has a 3-day lead time", uniform_lead_time=3),
    Scenario("lead_time_all_14d", "Every item has a 14-day lead time", uniform_lead_time=14),
    Scenario("ordering_cost_2", "Ordering cost $2 per order", costs=CostSettings(ordering_cost=2.0)),
    Scenario("ordering_cost_25", "Ordering cost $25 per order", costs=CostSettings(ordering_cost=25.0)),
    Scenario("holding_rate_15", "Holding cost 15% of unit cost per year", costs=CostSettings(holding_cost_rate=0.15)),
    Scenario("holding_rate_35", "Holding cost 35% of unit cost per year", costs=CostSettings(holding_cost_rate=0.35)),
    *[Scenario(f"synthetic_seed_{s}", f"Synthetic parameters redrawn with seed {s}", synthetic_seed=s) for s in (1, 2, 3, 4)],
]


def scenario_params(daily: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
    params, _ = generate(daily, SyntheticConfig(seed=scenario.synthetic_seed), config.TEST_START)
    if scenario.uniform_lead_time is not None:
        params["lead_time_days"] = scenario.uniform_lead_time
    return params


def main() -> None:
    report = Report()
    daily = pd.read_parquet(config.PROCESSED_DIR / "sample_daily.parquet")
    contexts: dict[tuple, object] = {}
    all_runs, rows = [], []

    for sc in SCENARIOS:
        start = time.perf_counter()
        key = (sc.synthetic_seed, sc.uniform_lead_time)
        if key not in contexts:   # forecasts and error histories only depend on items' parameters
            contexts[key] = prepare(Report(), daily=daily, params=scenario_params(daily, sc))
        ctx = contexts[key]
        runs = pd.concat([run_policy(ctx, pol, sl, sc.costs, sc.uncertain_lead_time)
                          for pol in POLICIES for sl in SERVICE_LEVELS], ignore_index=True)
        runs["scenario"] = sc.name
        all_runs.append(runs)
        summary = summarize(runs)
        allc = summary[summary["demand_class"] == "all"]

        row = {"scenario": sc.name, "description": sc.description}
        for pol in POLICIES:
            row[f"max_fill_{pol}"] = allc.loc[allc["policy"] == pol, "fill_rate"].max()
        for pol, ref in COMPARISONS:
            cost = matched_difference(allc, pol, ref)
            stock = matched_difference(allc, pol, ref, target=cost["fill_rate"], value="avg_inventory_value")
            tag = f"{pol}_vs_{ref}"
            row[f"{tag}_fill"] = cost["fill_rate"]
            row[f"{tag}_cost_pct"] = cost["pct_diff"]
            row[f"{tag}_stock_pct"] = stock["pct_diff"]
        rows.append(row)
        print(f"{sc.name}: {time.perf_counter() - start:.0f} s")

    results = pd.DataFrame(rows)
    runs_all = pd.concat(all_runs, ignore_index=True)

    report.section("Scenarios (all SIMULATED). Each changes one assumption from the base case")
    for sc in SCENARIOS:
        report.add(f"{sc.name:22s} {sc.description}")

    report.section("Highest fill rate each policy reaches (at a 99% target)")
    report.add(results.set_index("scenario")[[f"max_fill_{p}" for p in POLICIES]]
               .rename(columns=lambda c: c.replace("max_fill_", "")).map("{:.2%}".format).to_string())

    for pol, ref in COMPARISONS:
        tag = f"{pol}_vs_{ref}"
        report.section(f"{pol} vs {ref}: difference at the same fill rate (negative = {pol} cheaper)")
        table = results.set_index("scenario")[[f"{tag}_fill", f"{tag}_cost_pct", f"{tag}_stock_pct"]]
        table.columns = ["matched fill rate", "total cost diff", "stock value diff"]
        report.add(table.apply(lambda c: c.map(("{:.2%}" if c.name == "matched fill rate" else "{:+.1%}").format)).to_string())

    report.section(f"Bootstrap over items, base case ({N_BOOT} resamples, seed {config.SEED})")
    base_runs = runs_all[runs_all["scenario"] == "base"]
    base = results.set_index("scenario").loc["base"]
    boot_rows = []
    for pol, ref in COMPARISONS:
        target = base[f"{pol}_vs_{ref}_fill"]
        draws = bootstrap_matched(base_runs, pol, ref, target, N_BOOT, config.SEED)
        valid = draws[~np.isnan(draws)]
        low, high = np.percentile(valid, [2.5, 97.5])
        boot_rows.append({"comparison": f"{pol} vs {ref}", "fill_rate": target,
                          "estimate": base[f"{pol}_vs_{ref}_cost_pct"], "ci_low": low, "ci_high": high,
                          "share_cheaper": (valid < 0).mean(), "valid_resamples": valid.size})
        report.add(f"{pol} vs {ref} at {target:.2%} fill: {base[f'{pol}_vs_{ref}_cost_pct']:+.2%}"
                   f"  95% CI [{low:+.2%}, {high:+.2%}]  cheaper in {(valid < 0).mean():.0%} of"
                   f" {valid.size} valid resamples")
    boot = pd.DataFrame(boot_rows)

    out = config.RESULTS_DIR
    results.to_csv(out / "sensitivity_results.csv", index=False)
    boot.to_csv(out / "sensitivity_bootstrap.csv", index=False)
    runs_all.to_csv(out / "sensitivity_item_runs.csv.gz", index=False)
    plot(results, "docs/figures/07_sensitivity.png")
    report.save(out / "sensitivity_report.txt")
    print(f"\nSaved results to {out} and figure to docs/figures/07_sensitivity.png")


def plot(results: pd.DataFrame, path: str) -> None:
    series = [("engine_rf_vs_baseline_demand_sd", "RF engine vs textbook baseline", "#E69F00", -0.15),
              ("engine_rf_vs_engine_ma28", "RF engine vs MA-28 engine", "#0072B2", 0.15)]
    y = np.arange(len(results))[::-1]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for tag, label, color, offset in series:
        ax.scatter(results[f"{tag}_cost_pct"] * 100, y + offset, color=color, s=40, label=label, zorder=3)
    ax.axvline(0, color="#555555", lw=1)
    ax.set_yticks(y, results["scenario"])
    ax.set_xlabel("Total cost difference at the same fill rate, % (negative = RF engine cheaper)")
    ax.set_title("SIMULATED sensitivity of the cost difference", fontsize=11, fontweight="bold", pad=28)
    ax.grid(axis="x", color="#e5e5e5")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
