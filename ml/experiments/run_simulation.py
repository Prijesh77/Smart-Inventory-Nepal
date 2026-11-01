"""Simulate the test year under three reorder policies and several service levels.

All results are SIMULATED (synthetic costs, lead times and starting stock;
real M5 sales as demand). Unmet demand is a lost sale.

Policies (same (R, s, S) mechanics, weekly review, same order-size rule):
  baseline_demand_sd  textbook: 28-day average demand rate; safety stock from
                      the std of raw daily demand over the last 28 days x sqrt(P)
  engine_ma28         28-day average forecast; safety stock from the measured
                      RMSE of past out-of-sample forecast errors over P days
  engine_rf           Random Forest forecast; safety stock as engine_ma28

Comparing baseline vs engine_ma28 isolates the safety-stock method;
engine_ma28 vs engine_rf isolates the forecasting model.

No decision uses information from the day it is made or later:
  - forecasts at a review on day d use sales up to d-1
  - forecast-error history uses validation-period backtests plus test-year
    review forecasts whose whole P-day window ended before day d

Simplification: forecasts are built from the recorded M5 sales history, not
from the simulated (possibly stocked-out) sales.

    python -m ml.experiments.run_simulation
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ml import config  # noqa: E402
from ml.data.inspect_m5 import Report  # noqa: E402
from ml.evaluation.backtest import build_sales_matrix  # noqa: E402
from ml.features.build import build_rows, make_panel  # noqa: E402
from ml.inventory import formulas as f  # noqa: E402
from ml.inventory.recommend import ItemState, PolicySettings, recommend  # noqa: E402
from ml.inventory.simulation import CostSettings, SimItem, simulate_item  # noqa: E402
from ml.inventory.synthetic import SYNTHETIC_DIR  # noqa: E402
from ml.models.baselines import moving_average  # noqa: E402
from ml.models.forest import predict  # noqa: E402

REVIEW_DAYS = 7
FORECAST_DAYS = 28
# Low targets are included so the policies' fill-rate ranges overlap enough
# to compare their cost at the same achieved fill rate.
SERVICE_LEVELS = (0.60, 0.70, 0.80, 0.90, 0.95, 0.98, 0.99)
POLICIES = ("baseline_demand_sd", "engine_ma28", "engine_rf")
POLICY_COLORS = {"baseline_demand_sd": "#888888", "engine_ma28": "#0072B2", "engine_rf": "#E69F00"}
CLASS_ORDER = ["all", "smooth", "erratic", "intermittent", "lumpy"]


@dataclass
class Context:
    """Everything the policies may look at, prepared once, indexed [review, item]."""

    params: pd.DataFrame          # synthetic item parameters, same order as items
    demand: np.ndarray            # items x test days (0 when unavailable/closed)
    review: np.ndarray            # test days: True on review days
    origins: list[int]            # day number of each review
    protection: np.ndarray        # P = L + R per item
    forecasts: dict[str, np.ndarray]   # model -> reviews x items x FORECAST_DAYS
    period_sigma: dict[str, np.ndarray]  # model -> reviews x items
    base_level: np.ndarray        # reviews x items: 28-day mean demand
    base_sd: np.ndarray           # reviews x items: 28-day std of daily demand


def period_errors(forecast: np.ndarray, actual: np.ndarray, days: np.ndarray) -> np.ndarray:
    """Error of the P-day total (forecast - actual) per item; forecast/actual are [..., items, h]."""
    idx = (days - 1)[:, None]
    f_sum = np.take_along_axis(np.cumsum(forecast, axis=-1), np.broadcast_to(idx, forecast.shape[:-1] + (1,)), -1)
    a_sum = np.take_along_axis(np.cumsum(actual, axis=-1), np.broadcast_to(idx, actual.shape[:-1] + (1,)), -1)
    return (f_sum - a_sum)[..., 0]


def prepare(report: Report, daily: pd.DataFrame | None = None, params: pd.DataFrame | None = None) -> Context:
    """Build forecasts and error histories. `params` defaults to the saved synthetic parameters."""
    if daily is None:
        daily = pd.read_parquet(config.PROCESSED_DIR / "sample_daily.parquet")
    if params is None:
        params = pd.read_csv(SYNTHETIC_DIR / "item_inventory_params.csv")
    params = params.sort_values("item_id").reset_index(drop=True)
    panel = make_panel(daily, config.LAST_DAY)
    if list(panel.item_ids) != params["item_id"].tolist():
        raise ValueError("Synthetic parameters do not match the sampled items; rerun ml.inventory.synthetic")

    sales = build_sales_matrix(daily, config.LAST_DAY).to_numpy()
    actual = np.nan_to_num(sales)                 # unavailable -> no demand
    open_day = daily.drop_duplicates("d_num").set_index("d_num")["is_store_open"].reindex(
        range(1, config.LAST_DAY + 1)).fillna(True).to_numpy(dtype=bool)
    protection = params["lead_time_days"].to_numpy() + REVIEW_DAYS
    max_p = int(protection.max())

    def closed_mask(origin: int, horizon: int) -> np.ndarray:
        days = np.arange(origin, origin + horizon)
        inside = days <= config.LAST_DAY
        mask = np.zeros(horizon, dtype=bool)
        mask[inside] = ~open_day[days[inside] - 1]
        return mask

    rf_val = joblib.load(config.MODELS_DIR / "random_forest_v1.joblib")
    rf_final = joblib.load(config.MODELS_DIR / "random_forest_v1_final.joblib")
    n_items = len(params)

    # ---- forecast-error history from the validation period (out-of-sample)
    # Daily origins whose max_p-day window ends before the test year. RF errors
    # come from the model fitted on training data only.
    val_origins = list(range(config.VALIDATION_START, config.TEST_START - max_p + 1))
    rows = build_rows(panel, val_origins, max_p)
    rf_fc = np.clip(predict(rf_val, rows), 0, None).reshape(len(val_origins), n_items, max_p)
    ma_fc = np.stack([moving_average(sales[:, : o - 1], max_p, 28) for o in val_origins])
    act = np.stack([actual[:, o - 1: o - 1 + max_p] for o in val_origins])
    closed = np.stack([closed_mask(o, max_p) for o in val_origins])[:, None, :]
    val_errors = {
        "rf": period_errors(np.where(closed, 0, rf_fc), act, protection),
        "ma28": period_errors(np.where(closed, 0, ma_fc), act, protection),
    }

    # ---- test-year review forecasts (origin = review day, history up to the day before)
    origins = list(range(config.TEST_START, config.LAST_DAY + 1, REVIEW_DAYS))
    fc = {"rf": np.zeros((len(origins), n_items, FORECAST_DAYS)), "ma28": np.zeros((len(origins), n_items, FORECAST_DAYS))}
    base_level = np.zeros((len(origins), n_items))
    base_sd = np.zeros((len(origins), n_items))
    for r, o in enumerate(origins):
        horizon = min(FORECAST_DAYS, config.LAST_DAY - o + 1)
        pred = np.clip(predict(rf_final, build_rows(panel, [o], horizon)), 0, None).reshape(n_items, horizon)
        if horizon < FORECAST_DAYS:   # days after the dataset ends: repeat the recent forecast level
            pad = np.repeat(pred[:, -min(7, horizon):].mean(axis=1, keepdims=True), FORECAST_DAYS - horizon, axis=1)
            pred = np.concatenate([pred, pad], axis=1)
        closed = closed_mask(o, FORECAST_DAYS)
        fc["rf"][r] = np.where(closed, 0, pred)
        fc["ma28"][r] = np.where(closed, 0, moving_average(sales[:, : o - 1], FORECAST_DAYS, 28))
        window = sales[:, o - 29: o - 1]
        with np.errstate(invalid="ignore"):
            base_level[r] = np.nan_to_num(np.nanmean(window, axis=1))
            base_sd[r] = np.nan_to_num(np.nanstd(window, axis=1))

    # ---- measured P-day forecast-error RMSE available at each review
    period_sigma = {}
    for model in ("rf", "ma28"):
        test_err = np.full((len(origins), n_items), np.nan)
        for r, o in enumerate(origins):
            ends = o + protection - 1
            act_r = np.zeros((n_items, FORECAST_DAYS))
            span = min(FORECAST_DAYS, config.LAST_DAY - o + 1)
            act_r[:, :span] = actual[:, o - 1: o - 1 + span]
            err = period_errors(fc[model][r], act_r, protection)
            test_err[r] = np.where(ends <= config.LAST_DAY, err, np.nan)
        sig = np.zeros((len(origins), n_items))
        for r, o in enumerate(origins):
            for i in range(n_items):
                matured = [test_err[q, i] for q in range(r) if origins[q] + protection[i] <= o]
                pool = np.concatenate([val_errors[model][:, i], np.array(matured)])
                sig[r, i] = f.period_sigma_from_errors(pool)
        period_sigma[model] = sig

    test_slice = slice(config.TEST_START - 1, config.LAST_DAY)
    demand = np.where(open_day[test_slice], actual[:, test_slice], 0.0)
    review = (np.arange(demand.shape[1]) % REVIEW_DAYS) == 0

    report.section("Setup (all inventory values SIMULATED)")
    report.add(f"Items: {n_items}; test days: {demand.shape[1]} (d_{config.TEST_START}-d_{config.LAST_DAY})")
    report.add(f"Reviews: every {REVIEW_DAYS} days, {len(origins)} reviews; unmet demand = lost sale")
    report.add(f"Lead times (fixed): {sorted(params['lead_time_days'].unique().tolist())} days; protection period P = L + 7")
    report.add(f"Forecast-error history: {len(val_origins)} validation origins per item, plus matured test reviews")
    report.add(f"Total test-year demand: {demand.sum():,.0f} units")
    return Context(params, demand, review, origins, protection, fc, period_sigma, base_level, base_sd)


def actual_lead_times(ctx: Context, i: int, uncertain: bool, seed: int) -> np.ndarray:
    """Lead time for an order placed on each test day for item i.

    Fixed: the supplier's planned lead time. Uncertain: drawn from
    Normal(planned, supplier SD), rounded, at least 1 day. The draws depend
    only on (seed, item), so every policy faces the same delays (common
    random numbers), which makes the comparison fairer.
    """
    planned = int(ctx.params.at[i, "lead_time_days"])
    n = ctx.demand.shape[1]
    if not uncertain:
        return np.full(n, planned)
    sd = float(ctx.params.at[i, "lead_time_sd_days"])
    draws = np.random.default_rng([seed, i]).normal(planned, sd, size=n)
    return np.maximum(1, np.rint(draws)).astype(int)


def run_policy(ctx: Context, policy: str, service_level: float, costs: CostSettings,
               uncertain_lead_time: bool = False, seed: int = config.SEED) -> pd.DataFrame:
    """Simulate every item under one policy. Policies always plan with the
    planned lead time; with `uncertain_lead_time` the real delays vary."""
    settings = PolicySettings(service_level=service_level, review_period_days=REVIEW_DAYS,
                              ordering_cost=costs.ordering_cost, holding_cost_rate=costs.holding_cost_rate)
    records = []
    for i, p in ctx.params.iterrows():
        def decide(t: int, on_hand: float, on_order: float, i: int = i, p: pd.Series = p) -> int:
            r = t // REVIEW_DAYS
            state = ItemState(sku=p["item_id"], name=p["item_id"], on_hand=on_hand, on_order=on_order,
                              lead_time_days=int(p["lead_time_days"]), unit_cost=float(p["unit_cost"]),
                              min_order_qty=int(p["min_order_qty"]), pack_size=int(p["pack_size"]),
                              demand_class=p["demand_class"])
            if policy == "baseline_demand_sd":
                flat = np.full(FORECAST_DAYS, ctx.base_level[r, i])
                return recommend(state, flat, ctx.base_sd[r, i], settings).suggested_qty
            model = "rf" if policy == "engine_rf" else "ma28"
            return recommend(state, ctx.forecasts[model][r, i], None, settings,
                             period_sigma=ctx.period_sigma[model][r, i]).suggested_qty

        item = SimItem(p["item_id"], float(p["unit_cost"]), float(p["mean_price"]), float(p["initial_on_hand"]))
        lead = actual_lead_times(ctx, i, uncertain_lead_time, seed)
        out = simulate_item(ctx.demand[i], ctx.review, lead, item, decide, costs)
        records.append({"policy": policy, "service_level": service_level, "item_id": p["item_id"],
                        "demand_class": p["demand_class"], **out})
    return pd.DataFrame(records)


def summarize(runs: pd.DataFrame) -> pd.DataFrame:
    """Pool item results per policy, service level and demand class (plus 'all')."""
    sums = ["demand", "units_sold", "units_lost", "stockout_days", "days", "avg_inventory_value",
            "n_orders", "holding_cost", "ordering_cost", "total_cost", "lost_margin"]
    keys = ["policy", "service_level"]
    pooled = pd.concat([
        runs.groupby(keys)[sums].sum().assign(demand_class="all").reset_index(),
        runs.groupby(keys + ["demand_class"])[sums].sum().reset_index(),
    ])
    pooled["fill_rate"] = pooled["units_sold"] / pooled["demand"]
    pooled["stockout_rate"] = pooled["stockout_days"] / pooled["days"]
    # Lost sales valued only at lost gross margin (ignores lost goodwill), so a lower bound.
    pooled["cost_incl_lost_margin"] = pooled["total_cost"] + pooled["lost_margin"]
    return pooled


def cost_at_fill_rate(summary: pd.DataFrame, targets: tuple[float, ...]) -> pd.DataFrame:
    """Total cost each policy needs for a given fill rate, by linear interpolation
    between simulated service levels (NaN if outside the simulated range)."""
    rows = []
    for policy, part in summary[summary["demand_class"] == "all"].groupby("policy"):
        part = part.sort_values("fill_rate")
        x = part["fill_rate"].to_numpy()
        for target in targets:
            inside = x.min() <= target <= x.max()
            rows.append({
                "policy": policy, "target_fill_rate": target,
                "total_cost": np.interp(target, x, part["total_cost"]) if inside else np.nan,
                "avg_inventory_value": np.interp(target, x, part["avg_inventory_value"]) if inside else np.nan,
            })
    return pd.DataFrame(rows).pivot(index="policy", columns="target_fill_rate")


def plot_tradeoff(summary: pd.DataFrame, path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    allc = summary[summary["demand_class"] == "all"]
    label_offset = {"baseline_demand_sd": (4, -11), "engine_ma28": (-22, 4), "engine_rf": (4, -11)}
    for policy in POLICIES:
        part = allc[allc["policy"] == policy].sort_values("service_level")
        ax.plot(part["fill_rate"] * 100, part["total_cost"], marker="o", ms=6, lw=2,
                color=POLICY_COLORS[policy], label=policy)
        for _, row in part.iterrows():
            ax.annotate(f"{row['service_level']:.0%}", (row["fill_rate"] * 100, row["total_cost"]),
                        textcoords="offset points", xytext=label_offset[policy], fontsize=7, color="#555555")
    ax.set_xlabel("Fill rate (% of demand served)")
    ax.set_ylabel("Total modelled cost, $ (holding + ordering)")
    ax.set_title("SIMULATED cost vs service trade-off, test year (labels: target service level)",
                 fontsize=10, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#e5e5e5")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    report = Report()
    start = time.perf_counter()
    ctx = prepare(report)
    report.add(f"Preparation time: {time.perf_counter() - start:.0f} s")

    costs = CostSettings()
    start = time.perf_counter()
    runs = pd.concat([run_policy(ctx, pol, sl, costs) for pol in POLICIES for sl in SERVICE_LEVELS], ignore_index=True)
    report.add(f"Simulation time: {time.perf_counter() - start:.0f} s "
               f"({len(POLICIES)} policies x {len(SERVICE_LEVELS)} service levels x {len(ctx.params)} items)")
    summary = summarize(runs)

    cols = {"fill_rate": "{:.2%}", "stockout_rate": "{:.2%}", "units_lost": "{:,.0f}",
            "avg_inventory_value": "${:,.0f}", "n_orders": "{:,.0f}", "holding_cost": "${:,.0f}",
            "ordering_cost": "${:,.0f}", "total_cost": "${:,.0f}", "lost_margin": "${:,.0f}",
            "cost_incl_lost_margin": "${:,.0f}"}
    report.section("All items: results by policy and target service level (SIMULATED)")
    table = summary[summary["demand_class"] == "all"].set_index(["policy", "service_level"])[list(cols)]
    report.add(table.apply(lambda c: c.map(cols[c.name].format)).to_string())

    report.section("Cost needed to reach a given fill rate (interpolated, SIMULATED)")
    report.add("NaN = the policy never reached that fill rate at the simulated service levels")
    report.add(cost_at_fill_rate(summary, (0.990, 0.992, 0.995)).round(0).to_string())

    report.section("By demand class at 95% target service level (SIMULATED)")
    by_class = summary[summary["service_level"] == 0.95].set_index(["demand_class", "policy"])
    by_class = by_class.loc[[c for c in CLASS_ORDER if c in by_class.index.get_level_values(0)]]
    report.add(by_class[["fill_rate", "avg_inventory_value", "total_cost", "units_lost", "cost_incl_lost_margin"]]
               .apply(lambda c: c.map(cols[c.name].format)).to_string())

    out = config.RESULTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    runs.to_csv(out / "simulation_item_runs.csv", index=False)
    summary.to_csv(out / "simulation_summary.csv", index=False)
    plot_tradeoff(summary, "docs/figures/06_cost_vs_fill_rate.png")
    report.save(out / "simulation_report.txt")
    print(f"\nSaved results to {out} and figure to docs/figures/06_cost_vs_fill_rate.png")


if __name__ == "__main__":
    main()
