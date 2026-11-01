"""Load the project data into the database.

What is loaded, and where it comes from:
  categories, calendar_days, daily_sales   real M5 data (store CA_1, 267 sampled items)
  products (price)                         real M5 price on the last day of data
  suppliers, unit cost, pack size, MOQ     SIMULATED parameters (data/synthetic, seed 42)
  opening stock                            SIMULATED: stock left at the end of the test-year
                                           simulation (RF engine, 95% target); recorded as an
                                           'initial' inventory transaction
  model_evaluations                        Phase 3 backtest scores (experiments/results)
  app_settings                             default policy settings

The app's "today" is the day after the last day of data (2016-05-23).

Run from the project root (after `alembic upgrade head`):
    .venv\\Scripts\\python.exe backend\\scripts\\seed.py            # refuses if data exists
    .venv\\Scripts\\python.exe backend\\scripts\\seed.py --reset    # wipes ALL app data first
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

import pandas as pd  # noqa: E402
from sqlalchemy import func, insert, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import (  # noqa: E402
    AppSetting, CalendarDay, Category, DailySales, InventoryBalance, InventoryTransaction,
    ModelEvaluation, Product, Supplier,
)
from app.models.enums import EvaluationPeriod, TransactionType  # noqa: E402
from ml import config  # noqa: E402
from ml.inventory.synthetic import SYNTHETIC_DIR  # noqa: E402

CATEGORY_NAMES = {"FOODS": "Foods", "HOBBIES": "Hobbies", "HOUSEHOLD": "Household"}
OPENING_POLICY, OPENING_SERVICE_LEVEL = "engine_rf", 0.95
DEFAULT_POLICY = {"service_level": 0.95, "review_period_days": 7, "ordering_cost": 10.0,
                  "holding_cost_rate": 0.25, "min_cycle_days": 7, "max_cycle_days": 28,
                  "excess_cover_days": 60, "forecast_horizons": [7, 14, 28],
                  "note": "Cost values are SIMULATED assumptions"}


def product_name(item_id: str) -> str:
    """M5 items are anonymised; build a readable label, e.g. FOODS_3_090 -> 'Foods 3 - Item 090'."""
    cat, dept, num = item_id.split("_")
    return f"{CATEGORY_NAMES.get(cat, cat.title())} {dept} - Item {num}"


def money(value: float) -> Decimal:
    return Decimal(str(round(float(value), 2)))


def load_inputs() -> dict[str, pd.DataFrame]:
    paths = {
        "daily": config.PROCESSED_DIR / "sample_daily.parquet",
        "params": SYNTHETIC_DIR / "item_inventory_params.csv",
        "suppliers": SYNTHETIC_DIR / "suppliers.csv",
        "calendar": config.RAW_M5_DIR / "calendar.csv",
        "sim": config.RESULTS_DIR / "simulation_item_runs.csv",
        "rf_val": config.RESULTS_DIR / "random_forest_validation_scores.csv",
        "rf_test": config.RESULTS_DIR / "random_forest_test_scores.csv",
    }
    missing = [str(p) for p in paths.values() if not (ROOT / p).exists()]
    if missing:
        raise SystemExit("Missing input files (run the Phase 2-4 scripts first):\n  " + "\n  ".join(missing))
    return {k: pd.read_parquet(ROOT / p) if p.suffix == ".parquet" else pd.read_csv(ROOT / p)
            for k, p in paths.items()}


def calendar_frame(raw: pd.DataFrame) -> pd.DataFrame:
    cal = raw.copy()
    cal["d_num"] = cal["d"].str[2:].astype(int)
    cal["date"] = pd.to_datetime(cal["date"]).dt.date
    return cal


def calendar_rows(cal: pd.DataFrame) -> list[dict]:
    return [
        {"day": r.date, "wm_yr_wk": int(r.wm_yr_wk),
         "event_name": r.event_name_1 if isinstance(r.event_name_1, str) else None,
         "event_type": r.event_type_1 if isinstance(r.event_type_1, str) else None,
         "snap": bool(getattr(r, f"snap_{config.STATE_ID}")),
         "is_store_open": not (r.date.month == 12 and r.date.day == 25)}   # D8: closed on Christmas
        for r in cal.itertuples()
    ]


def extend_calendar(session: Session) -> int:
    """Add calendar days that are missing (e.g. the 28 future M5 days); never changes existing rows."""
    cal = calendar_frame(pd.read_csv(ROOT / config.RAW_M5_DIR / "calendar.csv"))
    existing = set(session.scalars(select(CalendarDay.day)))
    rows = [r for r in calendar_rows(cal) if r["day"] not in existing]
    if rows:
        session.execute(insert(CalendarDay), rows)
    return len(rows)


def reset(session: Session) -> None:
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def seed(session: Session, data: dict[str, pd.DataFrame]) -> dict[str, int]:
    daily, params = data["daily"], data["params"]
    daily = daily.assign(item_id=daily["item_id"].astype(str), cat_id=daily["cat_id"].astype(str),
                         dept_id=daily["dept_id"].astype(str))

    # ---- categories and suppliers
    categories = {code: Category(code=code, name=CATEGORY_NAMES.get(code, code.title()))
                  for code in sorted(daily["cat_id"].unique())}
    suppliers = {r.supplier_id: Supplier(code=r.supplier_id, name=r.name, lead_time_days=int(r.lead_time_days),
                                         lead_time_sd_days=money(r.lead_time_sd_days))
                 for r in data["suppliers"].itertuples()}
    session.add_all([*categories.values(), *suppliers.values()])
    session.flush()

    # ---- calendar: every M5 day, including the 28 future days after the sales data
    cal = calendar_frame(data["calendar"])
    session.execute(insert(CalendarDay), calendar_rows(cal))
    day_of = dict(zip(cal["d_num"], cal["date"]))

    # ---- products: real last price, simulated cost/supplier/pack
    last_price = (daily[daily["sell_price"].notna()].sort_values("d_num")
                  .groupby("item_id")["sell_price"].last())
    products: dict[str, Product] = {}
    for r in params.itertuples():
        products[r.item_id] = Product(
            sku=r.item_id, name=product_name(r.item_id), category=categories[r.cat_id], department=r.dept_id,
            supplier=suppliers[r.supplier_id], unit_price=money(last_price[r.item_id]),
            unit_cost=money(r.unit_cost), min_order_qty=int(r.min_order_qty), pack_size=int(r.pack_size),
            demand_class=r.demand_class,
        )
    session.add_all(products.values())
    session.flush()
    product_id = {sku: p.id for sku, p in products.items()}

    # ---- daily sales (real), in chunks
    rows = [{"product_id": product_id[r.item_id], "sales_date": day_of[r.d_num], "units": int(r.sales),
             "unit_price": money(r.sell_price) if pd.notna(r.sell_price) else None,
             "is_available": bool(r.is_available)}
            for r in daily[daily["item_id"].isin(product_id)].itertuples()]
    for start in range(0, len(rows), 20_000):
        session.execute(insert(DailySales), rows[start:start + 20_000])

    # ---- opening stock (SIMULATED end state) with an audit transaction for every product
    sim = data["sim"]
    sim = sim[(sim["policy"] == OPENING_POLICY) & (sim["service_level"] == OPENING_SERVICE_LEVEL)]
    ending = sim.set_index("item_id")["ending_on_hand"].round().astype(int)
    reason = (f"Opening balance: SIMULATED stock at the end of the test-year simulation "
              f"({OPENING_POLICY}, {OPENING_SERVICE_LEVEL:.0%} target)")
    for sku, pid in product_id.items():
        qty = int(ending.get(sku, 0))
        session.add(InventoryBalance(product_id=pid, on_hand=qty, backorders=0))
        if qty > 0:
            session.add(InventoryTransaction(product_id=pid, txn_type=TransactionType.INITIAL,
                                             quantity=qty, balance_after=qty, reason=reason))

    # ---- model evaluation scores from Phase 3
    evaluations = []
    for period, frame in [(EvaluationPeriod.VALIDATION, data["rf_val"]), (EvaluationPeriod.TEST, data["rf_test"])]:
        for r in frame.itertuples():
            version = "v1" if r.model.startswith("random_forest") else "baseline"
            evaluations.append({"model_name": r.model, "model_version": version, "period": period,
                                "horizon_days": int(r.horizon), "demand_class": r.demand_class,
                                "n_observations": int(r.n), "mae": r.mae, "rmse": r.rmse,
                                "wape": r.wape, "bias_pct": r.bias_pct})
    session.execute(insert(ModelEvaluation), evaluations)

    session.add(AppSetting(key="policy_defaults", value=DEFAULT_POLICY))
    session.flush()
    return {
        "categories": len(categories), "suppliers": len(suppliers), "calendar_days": len(cal),
        "products": len(products), "daily_sales": len(rows),
        "products_with_stock": int((ending.reindex(list(product_id)).fillna(0) > 0).sum()),
        "model_evaluations": len(evaluations),
        "app_today": str(day_of[config.LAST_DAY] + timedelta(days=1)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the database with project data.")
    parser.add_argument("--reset", action="store_true", help="delete ALL existing app data first")
    parser.add_argument("--extend-calendar", action="store_true",
                        help="only add missing calendar days (safe on a seeded database)")
    args = parser.parse_args()

    if args.extend_calendar:
        with Session(get_engine()) as session, session.begin():
            print(f"Calendar days added: {extend_calendar(session)}")
        return

    data = load_inputs()
    engine = get_engine()
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    start = time.perf_counter()
    with Session(engine) as session, session.begin():   # one transaction: all or nothing
        existing = session.scalar(select(func.count()).select_from(Product))
        if existing and not args.reset:
            raise SystemExit(f"Database already has {existing} products. Use --reset to wipe and reload.")
        if args.reset:
            reset(session)
            print("Existing data removed.")
        counts = seed(session, data)
    for key, value in counts.items():
        print(f"  {key:22s} {value}")
    print(f"Seeded in {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main()
