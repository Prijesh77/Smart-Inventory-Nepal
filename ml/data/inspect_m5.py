"""Inspect the raw M5 files before writing any cleaning code.

This script only reads and reports. It does not change or save any data
except the optional text report. Run it from the project root:

    python -m ml.data.inspect_m5 --raw-dir data/raw/m5 --report docs/02_m5_inspection_report.txt
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CALENDAR_FILE = "calendar.csv"
PRICES_FILE = "sell_prices.csv"
SALES_FILE = "sales_train_evaluation.csv"
REQUIRED_FILES = (CALENDAR_FILE, PRICES_FILE, SALES_FILE)

# Columns we expect from the Kaggle documentation. The script reports any
# difference instead of assuming these are correct.
EXPECTED_SALES_ID_COLUMNS = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
EXPECTED_PRICE_COLUMNS = ["store_id", "item_id", "wm_yr_wk", "sell_price"]
EXPECTED_CALENDAR_COLUMNS = [
    "date", "wm_yr_wk", "weekday", "wday", "month", "year", "d",
    "event_name_1", "event_type_1", "event_name_2", "event_type_2",
    "snap_CA", "snap_TX", "snap_WI",
]


class Report:
    """Collects printed lines so they can also be saved to a file."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def section(self, title: str) -> None:
        self.add()
        self.add("=" * 70)
        self.add(title)
        self.add("=" * 70)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def check_files(raw_dir: Path) -> dict[str, int | None]:
    """Return the size in bytes of each required file, or None if missing."""
    sizes: dict[str, int | None] = {}
    for name in REQUIRED_FILES:
        path = raw_dir / name
        sizes[name] = path.stat().st_size if path.exists() else None
    return sizes


def compare_columns(actual: list[str], expected: list[str]) -> tuple[list[str], list[str]]:
    """Return (missing expected columns, unexpected extra columns)."""
    missing = [c for c in expected if c not in actual]
    extra = [c for c in actual if c not in expected]
    return missing, extra


def day_columns(columns: list[str]) -> list[str]:
    """Return the d_1, d_2, ... columns in numeric order."""
    days = [c for c in columns if c.startswith("d_") and c[2:].isdigit()]
    return sorted(days, key=lambda c: int(c[2:]))


def load_sales(path: Path) -> pd.DataFrame:
    """Load the wide sales file with compact dtypes to save memory."""
    header = pd.read_csv(path, nrows=0).columns.tolist()
    dtypes: dict[str, str] = {c: "int32" for c in day_columns(header)}
    dtypes.update({c: "category" for c in header if c in EXPECTED_SALES_ID_COLUMNS and c != "id"})
    return pd.read_csv(path, dtype=dtypes)


def leading_zero_stats(sales_values: np.ndarray) -> dict[str, float | int]:
    """Measure zeros before each series' first sale.

    A zero before the first sale usually means the item was not yet on the
    shelf, so it should not count as zero demand. Zeros after the first sale
    are ambiguous: genuine zero demand or an unrecorded stockout.
    """
    has_sale = sales_values > 0
    ever_sold = has_sale.any(axis=1)
    n_days = sales_values.shape[1]
    # argmax returns 0 for rows with no sale, so treat those rows separately.
    first_sale_idx = np.where(ever_sold, has_sale.argmax(axis=1), n_days)

    total_cells = sales_values.size
    leading_zero_cells = int(first_sale_idx.sum())
    active_cells = total_cells - leading_zero_cells
    zeros_total = int((sales_values == 0).sum())
    zeros_after_first_sale = zeros_total - leading_zero_cells

    return {
        "series": int(sales_values.shape[0]),
        "never_sold": int((~ever_sold).sum()),
        "zero_share_all_cells": zeros_total / total_cells,
        "leading_zero_share": leading_zero_cells / total_cells,
        "zero_share_after_first_sale": zeros_after_first_sale / active_cells if active_cells else float("nan"),
        "median_first_sale_day": float(np.median(first_sale_idx[ever_sold]) + 1) if ever_sold.any() else float("nan"),
    }


def inspect_calendar(cal: pd.DataFrame, report: Report) -> None:
    report.section("calendar.csv")
    report.add(f"Shape: {cal.shape[0]:,} rows x {cal.shape[1]} columns")
    missing, extra = compare_columns(cal.columns.tolist(), EXPECTED_CALENDAR_COLUMNS)
    report.add(f"Columns: {cal.columns.tolist()}")
    report.add(f"Missing expected columns: {missing or 'none'}")
    report.add(f"Unexpected columns: {extra or 'none'}")
    report.add(f"Dtypes:\n{cal.dtypes.to_string()}")

    dates = pd.to_datetime(cal["date"])
    report.add(f"Date range: {dates.min().date()} -> {dates.max().date()}")
    gaps = dates.diff().dropna().dt.days
    report.add(f"Dates strictly daily with no gaps: {bool((gaps == 1).all())}")
    report.add(f"Duplicate 'd' labels: {int(cal['d'].duplicated().sum())}")

    report.add("Missing values per column:")
    report.add(cal.isna().sum().to_string())
    report.add("(Missing event_name values are expected: most days have no event.)")

    if "event_type_1" in cal:
        report.add("Days per event_type_1:")
        report.add(cal["event_type_1"].value_counts().to_string())
    snap_cols = [c for c in cal.columns if c.startswith("snap_")]
    for col in snap_cols:
        report.add(f"{col}: {int(cal[col].sum())} SNAP days out of {len(cal)}")


def inspect_prices(prices: pd.DataFrame, report: Report) -> None:
    report.section("sell_prices.csv")
    report.add(f"Shape: {prices.shape[0]:,} rows x {prices.shape[1]} columns")
    missing, extra = compare_columns(prices.columns.tolist(), EXPECTED_PRICE_COLUMNS)
    report.add(f"Columns: {prices.columns.tolist()}")
    report.add(f"Missing expected columns: {missing or 'none'}")
    report.add(f"Unexpected columns: {extra or 'none'}")
    report.add(f"Dtypes:\n{prices.dtypes.to_string()}")
    report.add(f"Missing values:\n{prices.isna().sum().to_string()}")

    key = ["store_id", "item_id", "wm_yr_wk"]
    report.add(f"Duplicate (store, item, week) rows: {int(prices.duplicated(key).sum()):,}")
    report.add(f"Stores: {prices['store_id'].nunique()}, items: {prices['item_id'].nunique():,}")
    report.add(f"Week range: {prices['wm_yr_wk'].min()} -> {prices['wm_yr_wk'].max()}")
    report.add("sell_price summary:")
    report.add(prices["sell_price"].describe().to_string())
    report.add(f"Non-positive prices: {int((prices['sell_price'] <= 0).sum())}")


def inspect_sales(sales: pd.DataFrame, report: Report) -> None:
    report.section("sales_train_evaluation.csv")
    days = day_columns(sales.columns.tolist())
    id_cols = [c for c in sales.columns if c not in days]
    report.add(f"Shape: {sales.shape[0]:,} rows x {sales.shape[1]:,} columns")
    report.add(f"ID columns: {id_cols}")
    missing, _ = compare_columns(id_cols, EXPECTED_SALES_ID_COLUMNS)
    report.add(f"Missing expected ID columns: {missing or 'none'}")
    report.add(f"Day columns: {len(days)} ({days[0]} -> {days[-1]})")
    report.add(f"Memory used: {sales.memory_usage(deep=True).sum() / 1e6:,.0f} MB")

    report.add(f"Duplicate ids: {int(sales['id'].duplicated().sum())}")
    report.add(f"Missing values in ID columns: {int(sales[id_cols].isna().sum().sum())}")
    report.add(f"Missing values in sales: {int(sales[days].isna().sum().sum())}")

    for col in ["state_id", "store_id", "cat_id", "dept_id", "item_id"]:
        if col in sales:
            report.add(f"Unique {col}: {sales[col].nunique():,}")
    report.add("Series per store:")
    report.add(sales["store_id"].value_counts().sort_index().to_string())
    report.add("Series per category in one store (items per category):")
    first_store = sorted(sales["store_id"].unique())[0]
    report.add(sales.loc[sales["store_id"] == first_store, "cat_id"].value_counts().to_string())

    values = sales[days].to_numpy()
    report.add(f"Negative sales values: {int((values < 0).sum())}")
    report.add(f"Max daily units for one item: {int(values.max())}")

    stats = leading_zero_stats(values)
    report.add("Zero-sales analysis:")
    report.add(f"  Series that never sold: {stats['never_sold']:,} of {stats['series']:,}")
    report.add(f"  Share of all cells that are zero: {stats['zero_share_all_cells']:.1%}")
    report.add(f"  Share of cells that are leading zeros (before first sale): {stats['leading_zero_share']:.1%}")
    report.add(f"  Zero share after each series' first sale: {stats['zero_share_after_first_sale']:.1%}")
    report.add(f"  Median day of first sale: d_{stats['median_first_sale_day']:.0f}")


def inspect_cross_file(sales: pd.DataFrame, prices: pd.DataFrame, cal: pd.DataFrame, report: Report) -> None:
    """Check that the three files line up before we join them in cleaning."""
    report.section("Cross-file consistency")
    days = day_columns(sales.columns.tolist())
    cal_days = set(cal["d"])
    report.add(f"Sales day columns missing from calendar: {sum(d not in cal_days for d in days)}")
    report.add(f"Calendar days beyond the sales data (future/test period): {len(cal_days) - len(days)}")

    sales_pairs = set(zip(sales["store_id"].astype(str), sales["item_id"].astype(str)))
    price_pairs = set(zip(prices["store_id"].astype(str), prices["item_id"].astype(str)))
    report.add(f"Store-item series with no price rows at all: {len(sales_pairs - price_pairs):,}")
    report.add(f"Price store-items not in sales: {len(price_pairs - sales_pairs):,}")

    # Does the first price week match the first sale week? If prices start
    # when the item is listed, sales before that week should be zero.
    day_to_week = cal.set_index("d")["wm_yr_wk"]
    has_sale = sales[days].to_numpy() > 0
    ever_sold = has_sale.any(axis=1)
    first_sale_day = np.array(days)[has_sale.argmax(axis=1)]

    first_price = (
        prices.groupby(["store_id", "item_id"], observed=True)["wm_yr_wk"].min()
        .rename("first_price_week").reset_index()
    )
    first_price[["store_id", "item_id"]] = first_price[["store_id", "item_id"]].astype(str)
    series = pd.DataFrame({
        "store_id": sales["store_id"].astype(str).to_numpy(),
        "item_id": sales["item_id"].astype(str).to_numpy(),
        "ever_sold": ever_sold,
        "first_sale_week": day_to_week.reindex(first_sale_day).to_numpy(),
    }).merge(first_price, on=["store_id", "item_id"], how="left")

    sold = series[series["ever_sold"] & series["first_price_week"].notna()]
    before = int((sold["first_sale_week"] < sold["first_price_week"]).sum())
    same = int((sold["first_sale_week"] == sold["first_price_week"]).sum())
    report.add(f"Series whose first sale is before their first price week: {before:,}")
    report.add(f"Series whose first sale is in their first price week: {same:,} of {len(sold):,}")
    report.add(
        "Interpretation: if first sales almost never precede the first price week, "
        "price availability is a reliable signal for when an item was on sale."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect raw M5 files.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/m5"))
    parser.add_argument("--report", type=Path, default=None, help="Optional path to save the report as text.")
    args = parser.parse_args()

    report = Report()
    report.section("File check")
    sizes = check_files(args.raw_dir)
    for name, size in sizes.items():
        status = f"{size / 1e6:,.1f} MB" if size is not None else "MISSING"
        report.add(f"{name}: {status}")
    missing_files = [name for name, size in sizes.items() if size is None]
    if missing_files:
        report.add(f"\nPlease download {missing_files} from Kaggle into {args.raw_dir.resolve()}")
        raise SystemExit(1)

    cal = pd.read_csv(args.raw_dir / CALENDAR_FILE)
    prices = pd.read_csv(
        args.raw_dir / PRICES_FILE,
        dtype={"store_id": "category", "item_id": "category", "wm_yr_wk": "int32", "sell_price": "float32"},
    )
    sales = load_sales(args.raw_dir / SALES_FILE)

    inspect_calendar(cal, report)
    inspect_prices(prices, report)
    inspect_sales(sales, report)
    inspect_cross_file(sales, prices, cal, report)

    if args.report:
        report.save(args.report)
        print(f"\nReport saved to {args.report}")


if __name__ == "__main__":
    main()
