"""Clean and reshape one M5 store into a long daily table, then sample items.

Implements decisions D1-D7 from docs/02_data_quality_findings.md. Run from the
project root:

    python -m ml.data.clean_m5

Outputs (in data/processed/):
    item_demand_classes.csv   one row per item in the store, with demand class
    sample_items.csv          the stratified item sample used in experiments
    sample_daily.parquet      one row per sampled item per day
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ml import config
from ml.data.inspect_m5 import CALENDAR_FILE, PRICES_FILE, SALES_FILE, Report, day_columns

ID_COLUMNS = ["item_id", "dept_id", "cat_id"]
INSUFFICIENT = "insufficient_data"


def load_store_sales(path: Path, store_id: str) -> pd.DataFrame:
    """Load the wide sales file and keep one store."""
    header = pd.read_csv(path, nrows=0).columns.tolist()
    dtypes = {c: "int32" for c in day_columns(header)}
    wide = pd.read_csv(path, dtype=dtypes)
    wide = wide[wide["store_id"] == store_id].reset_index(drop=True)
    if wide.empty:
        raise ValueError(f"No sales rows for store {store_id!r}")
    return wide


def melt_sales(wide: pd.DataFrame) -> pd.DataFrame:
    """Reshape d_1 ... d_N columns into one row per item per day."""
    days = day_columns(wide.columns.tolist())
    long = wide.melt(id_vars=ID_COLUMNS, value_vars=days, var_name="d", value_name="sales")
    long["d_num"] = long["d"].str[2:].astype("int32")
    long[ID_COLUMNS] = long[ID_COLUMNS].astype(str)
    return long.drop(columns="d")


def add_calendar(long: pd.DataFrame, cal: pd.DataFrame, state_id: str) -> pd.DataFrame:
    """Attach dates, calendar features and the state's SNAP flag.

    A left join on the sales rows drops calendar days without actuals (D5).
    """
    cal = cal.copy()
    cal["d_num"] = cal["d"].str[2:].astype("int32")
    cal["date"] = pd.to_datetime(cal["date"])
    cal = cal.rename(columns={f"snap_{state_id}": "snap"})
    keep = ["d_num", "date", "wm_yr_wk", "wday", "month", "year",
            "event_name_1", "event_type_1", "event_name_2", "event_type_2", "snap"]
    return long.merge(cal[keep], on="d_num", how="left", validate="many_to_one")


def add_prices(long: pd.DataFrame, store_prices: pd.DataFrame) -> pd.DataFrame:
    """Attach the weekly price and flag whether the item was on sale that day.

    An item is available when it has a price that week and the store is open
    (D8: the store is closed on Christmas Day, so those zeros are not demand).
    """
    prices = store_prices[["item_id", "wm_yr_wk", "sell_price"]].copy()
    prices["item_id"] = prices["item_id"].astype(str)
    out = long.merge(prices, on=["item_id", "wm_yr_wk"], how="left", validate="many_to_one")
    out["is_store_open"] = ~((out["date"].dt.month == 12) & (out["date"].dt.day == 25))
    out["is_available"] = out["sell_price"].notna() & out["is_store_open"]
    return out


def trim_before_launch(long: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop days before each item's first price week (D1).

    Returns the trimmed table and counts that should be checked: any sales
    before launch would mean the price signal is not reliable.
    """
    listed = long["sell_price"].notna() if "sell_price" in long else long["is_available"]
    first_day = long.loc[listed, ["item_id", "d_num"]].groupby("item_id")["d_num"].min()
    launch = long["item_id"].map(first_day)
    before = long["d_num"] < launch
    stats = {
        "rows_removed": int(before.sum()),
        "units_sold_before_launch": int(long.loc[before, "sales"].sum()),
        "items_never_available": int(launch.isna().groupby(long["item_id"]).any().sum()),
    }
    return long.loc[~before & launch.notna()].reset_index(drop=True), stats


def assign_split(d_num: pd.Series) -> pd.Series:
    """Label each day train / validation / test using the config boundaries."""
    labels = np.select(
        [d_num <= config.TRAIN_END, d_num < config.TEST_START],
        ["train", "validation"],
        default="test",
    )
    return pd.Series(labels, index=d_num.index, dtype="category")


def classify_demand(train: pd.DataFrame) -> pd.DataFrame:
    """Classify each item's demand pattern using training data only (D7).

    ADI (average demand interval) = available days / days with a sale.
        High ADI means sales happen rarely.
    CV2 = (std / mean)^2 of the non-zero sale sizes.
        High CV2 means sale sizes vary a lot.

    Syntetos & Boylan (2005) cut-offs give four classes:
        smooth       ADI < 1.32 and CV2 < 0.49
        erratic      ADI < 1.32 and CV2 >= 0.49
        intermittent ADI >= 1.32 and CV2 < 0.49
        lumpy        ADI >= 1.32 and CV2 >= 0.49
    Population std (ddof=0) is used so a single sale gives CV2 = 0, not NaN.
    """
    avail = train[train["is_available"]]
    n_days = avail.groupby("item_id").size().rename("n_train_days")
    nonzero = avail[avail["sales"] > 0].groupby("item_id")["sales"]
    out = pd.concat(
        [
            n_days,
            nonzero.size().rename("n_nonzero_days"),
            avail.groupby("item_id")["sales"].sum().rename("total_units"),
            nonzero.mean().rename("size_mean"),
            nonzero.std(ddof=0).rename("size_std"),
        ],
        axis=1,
    ).fillna({"n_nonzero_days": 0, "total_units": 0})
    out["n_nonzero_days"] = out["n_nonzero_days"].astype(int)
    out["mean_daily_sales"] = out["total_units"] / out["n_train_days"]
    out["adi"] = out["n_train_days"] / out["n_nonzero_days"].replace(0, np.nan)
    out["cv2"] = (out["size_std"] / out["size_mean"]) ** 2

    enough = (out["n_train_days"] >= config.MIN_TRAIN_DAYS) & (out["n_nonzero_days"] >= config.MIN_NONZERO_DAYS)
    frequent = out["adi"] < config.ADI_CUTOFF
    variable = out["cv2"] >= config.CV2_CUTOFF
    out["demand_class"] = np.select(
        [~enough, frequent & ~variable, frequent & variable, ~frequent & ~variable],
        [INSUFFICIENT, "smooth", "erratic", "intermittent"],
        default="lumpy",
    )
    return out.drop(columns=["size_mean", "size_std"]).reset_index()


def stratified_sample(
    classes: pd.DataFrame, size: int, min_per_stratum: int, seed: int
) -> pd.DataFrame:
    """Sample items proportionally from each (category, demand class) stratum.

    Small strata get at least `min_per_stratum` items (or all of them) so every
    combination can be analysed. Items with insufficient data are excluded.
    """
    eligible = classes[classes["demand_class"] != INSUFFICIENT]
    total = len(eligible)
    parts = []
    for _, group in eligible.groupby(["cat_id", "demand_class"], sort=True):
        target = max(min_per_stratum, round(size * len(group) / total))
        parts.append(group.sample(n=min(target, len(group)), random_state=seed))
    return pd.concat(parts).sort_values("item_id").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean one M5 store and sample items.")
    parser.add_argument("--raw-dir", type=Path, default=config.RAW_M5_DIR)
    parser.add_argument("--out-dir", type=Path, default=config.PROCESSED_DIR)
    parser.add_argument("--report", type=Path, default=Path("docs/03_cleaning_report.txt"))
    args = parser.parse_args()
    report = Report()

    report.section(f"Load store {config.STORE_ID}")
    cal = pd.read_csv(args.raw_dir / CALENDAR_FILE)
    prices = pd.read_csv(args.raw_dir / PRICES_FILE, dtype={"wm_yr_wk": "int32", "sell_price": "float32"})
    store_prices = prices[prices["store_id"] == config.STORE_ID]
    wide = load_store_sales(args.raw_dir / SALES_FILE, config.STORE_ID)
    report.add(f"Items: {len(wide):,}, price rows: {len(store_prices):,}")

    long = melt_sales(wide)
    long = add_calendar(long, cal, config.STATE_ID)
    long = add_prices(long, store_prices)
    report.add(f"Long table before trimming: {len(long):,} rows")

    report.section("D1: trim days before each item's first price week")
    long, trim_stats = trim_before_launch(long)
    for key, value in trim_stats.items():
        report.add(f"{key}: {value:,}")
    report.add(f"Rows after trimming: {len(long):,}")

    report.section("D8: store-closed days (Christmas)")
    closed = long[~long["is_store_open"]]
    report.add(f"Closed dates: {sorted(closed['date'].dt.strftime('%Y-%m-%d').unique().tolist())}")
    report.add(f"Units sold on closed dates: {int(closed['sales'].sum()):,}")

    report.section("D2: unavailable days after launch (no price row)")
    gaps = long[long["sell_price"].isna()]
    report.add(f"Unavailable item-days: {len(gaps):,} ({len(gaps) / len(long):.2%} of rows)")
    report.add(f"Items with at least one unavailable day: {gaps['item_id'].nunique():,}")
    report.add(f"Units sold on unavailable days: {int(gaps['sales'].sum()):,}")
    report.add("These rows are kept for date continuity but excluded from training targets and metrics.")

    report.section("Price checks")
    low = long[long["sell_price"] < 0.10]
    report.add(f"Item-days with price below $0.10: {len(low):,} across {low['item_id'].nunique()} items")
    if not low.empty:
        report.add(low.groupby("item_id")["sell_price"].agg(["min", "max", "size"]).to_string())

    report.section("Largest single-day sales (D6 review)")
    top = long.nlargest(10, "sales")[["item_id", "date", "sales", "sell_price", "event_name_1", "snap"]]
    report.add(top.to_string(index=False))

    long["split"] = assign_split(long["d_num"])
    report.section("Chronological splits")
    split_dates = long.groupby("split", observed=True)["date"].agg(["min", "max"])
    report.add(split_dates.to_string())

    report.section("D7: demand classes (training period only)")
    classes = classify_demand(long[long["split"] == "train"])
    meta = wide[ID_COLUMNS].astype(str)
    classes = meta.merge(classes, on="item_id", how="left")
    classes["demand_class"] = classes["demand_class"].fillna(INSUFFICIENT)
    report.add(pd.crosstab(classes["cat_id"], classes["demand_class"], margins=True).to_string())

    sample = stratified_sample(classes, config.SAMPLE_SIZE, config.MIN_PER_STRATUM, config.SEED)
    report.section(f"Stratified sample (target {config.SAMPLE_SIZE}, seed {config.SEED})")
    report.add(f"Items sampled: {len(sample)}")
    report.add(pd.crosstab(sample["cat_id"], sample["demand_class"], margins=True).to_string())

    sample_daily = long[long["item_id"].isin(sample["item_id"])].copy()
    sample_daily = sample_daily.merge(sample[["item_id", "demand_class"]], on="item_id", how="left")
    for col in ["item_id", "dept_id", "cat_id", "demand_class",
                "event_name_1", "event_type_1", "event_name_2", "event_type_2"]:
        sample_daily[col] = sample_daily[col].astype("category")
    sample_daily = sample_daily.sort_values(["item_id", "d_num"]).reset_index(drop=True)

    observed = sample_daily[sample_daily["is_available"]]
    report.section("Sample daily table")
    report.add(f"Rows: {len(sample_daily):,}, columns: {sample_daily.columns.tolist()}")
    report.add("Zero-sales share on available days, by split:")
    report.add(observed.groupby("split", observed=True)["sales"].apply(lambda s: f"{(s == 0).mean():.1%}").to_string())

    args.out_dir.mkdir(parents=True, exist_ok=True)
    classes.to_csv(args.out_dir / "item_demand_classes.csv", index=False)
    sample.to_csv(args.out_dir / "sample_items.csv", index=False)
    sample_daily.to_parquet(args.out_dir / "sample_daily.parquet", index=False)
    report.section("Saved")
    for name in ["item_demand_classes.csv", "sample_items.csv", "sample_daily.parquet"]:
        report.add(str(args.out_dir / name))
    report.save(args.report)


if __name__ == "__main__":
    main()
