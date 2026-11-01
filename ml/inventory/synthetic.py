"""Generate SIMULATED inventory parameters for the sampled M5 items.

M5 has sales and prices but no stock levels, costs, suppliers or lead times.
These are generated here from documented rules and a fixed seed. Every value
is an assumption, never a retailer observation; reports must label results
that depend on them as "simulated".

Only data from before the test year is used, so the parameters cannot leak
information about the period the simulation evaluates.

    python -m ml.inventory.synthetic
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ml import config

SYNTHETIC_DIR = config.PROJECT_ROOT / "data" / "synthetic"


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    lead_time_days: int        # planned (mean) lead time
    lead_time_sd_days: float   # variability, used in lead-time sensitivity runs


@dataclass(frozen=True)
class SyntheticConfig:
    seed: int = config.SEED
    cost_share_low: float = 0.60       # unit cost = 60-70% of the average sell price
    cost_share_high: float = 0.70
    pack_options: tuple[int, ...] = (1, 6, 12, 24)
    pack_max_cover_days: int = 7       # a pack should not exceed ~one week of demand
    initial_cover_days: int = 21       # starting stock = 3 weeks of recent demand
    recent_days: int = 28              # "recent demand" window just before the test year
    suppliers: tuple[Supplier, ...] = field(default=(
        Supplier("SUP_A", "Supplier A", 3, 0.5),
        Supplier("SUP_B", "Supplier B", 5, 1.0),
        Supplier("SUP_C", "Supplier C", 7, 1.0),
        Supplier("SUP_D", "Supplier D", 10, 2.0),
        Supplier("SUP_E", "Supplier E", 14, 3.0),
    ))


def assign_suppliers(departments: list[str], suppliers: tuple[Supplier, ...], rng: np.random.Generator) -> dict[str, str]:
    """Each department buys from one supplier. Shuffled, then dealt out in turn so all suppliers are used."""
    order = rng.permutation(sorted(departments))
    return {dept: suppliers[i % len(suppliers)].supplier_id for i, dept in enumerate(order)}


def choose_pack_size(mean_daily: float, options: tuple[int, ...], max_cover_days: int) -> int:
    """Largest pack that holds no more than `max_cover_days` of demand (at least the smallest option).

    Slow items get single units; fast items come in cases. This keeps packs
    from forcing months of stock onto slow sellers.
    """
    fitting = [p for p in sorted(options) if p <= mean_daily * max_cover_days]
    return fitting[-1] if fitting else min(options)


def generate(daily: pd.DataFrame, cfg: SyntheticConfig, test_start: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (item parameters, supplier table) using only days before `test_start`."""
    rng = np.random.default_rng(cfg.seed)
    history = daily[(daily["d_num"] < test_start) & daily["is_available"]].copy()
    history["item_id"] = history["item_id"].astype(str)

    items = (
        history.groupby("item_id")
        .agg(dept_id=("dept_id", "first"), cat_id=("cat_id", "first"),
             demand_class=("demand_class", "first"),
             mean_price=("sell_price", "mean"), mean_daily_train=("sales", "mean"))
        .reset_index()
        .sort_values("item_id")
        .reset_index(drop=True)
    )
    for col in ["dept_id", "cat_id", "demand_class"]:
        items[col] = items[col].astype(str)

    recent = history[history["d_num"] >= test_start - cfg.recent_days]
    items["mean_daily_recent"] = items["item_id"].map(recent.groupby("item_id")["sales"].mean()).fillna(0.0)

    supplier_of = assign_suppliers(items["dept_id"].unique().tolist(), cfg.suppliers, rng)
    suppliers = pd.DataFrame([asdict(s) for s in cfg.suppliers])
    items["supplier_id"] = items["dept_id"].map(supplier_of)
    items = (
        items.merge(suppliers[["supplier_id", "lead_time_days", "lead_time_sd_days"]], on="supplier_id")
        .sort_values("item_id").reset_index(drop=True)   # fixed row order before random draws
    )

    share = rng.uniform(cfg.cost_share_low, cfg.cost_share_high, size=len(items))
    items["unit_cost"] = (items["mean_price"] * share).round(2)
    items["pack_size"] = [
        choose_pack_size(m, cfg.pack_options, cfg.pack_max_cover_days) for m in items["mean_daily_train"]
    ]
    items["min_order_qty"] = items["pack_size"]   # one pack minimum
    items["initial_on_hand"] = [math.ceil(m * cfg.initial_cover_days) for m in items["mean_daily_recent"]]

    columns = ["item_id", "dept_id", "cat_id", "demand_class", "supplier_id", "lead_time_days",
               "lead_time_sd_days", "mean_price", "unit_cost", "pack_size", "min_order_qty",
               "mean_daily_train", "mean_daily_recent", "initial_on_hand"]
    return items[columns].sort_values("item_id").reset_index(drop=True), suppliers


def main() -> None:
    cfg = SyntheticConfig()
    daily = pd.read_parquet(config.PROCESSED_DIR / "sample_daily.parquet")
    items, suppliers = generate(daily, cfg, config.TEST_START)

    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    items.to_csv(SYNTHETIC_DIR / "item_inventory_params.csv", index=False)
    suppliers.to_csv(SYNTHETIC_DIR / "suppliers.csv", index=False)
    (SYNTHETIC_DIR / "synthetic_config.json").write_text(
        json.dumps({**asdict(cfg), "test_start": config.TEST_START,
                    "note": "SIMULATED parameters; not retailer observations"}, indent=2),
        encoding="utf-8",
    )

    print("SIMULATED inventory parameters (not retailer data)\n")
    print(f"Items: {len(items)}\n")
    print("Suppliers and the departments they serve:")
    served = items.groupby("supplier_id")["dept_id"].unique().map(lambda d: ", ".join(sorted(d)))
    print(suppliers.set_index("supplier_id").assign(departments=served, items=items["supplier_id"].value_counts()).to_string())
    print("\nPack size (= minimum order) by demand class:")
    print(pd.crosstab(items["demand_class"], items["pack_size"]).to_string())
    print("\nUnit cost ($):")
    print(items["unit_cost"].describe().round(2).to_string())
    print(f"\nTotal initial stock: {items['initial_on_hand'].sum():,} units,"
          f" value ${(items['initial_on_hand'] * items['unit_cost']).sum():,.0f}")
    print(f"Items starting with zero stock (no recent sales): {(items['initial_on_hand'] == 0).sum()}")
    print(f"\nSaved to {SYNTHETIC_DIR}")


if __name__ == "__main__":
    main()
