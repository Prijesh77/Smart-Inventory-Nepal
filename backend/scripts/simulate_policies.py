"""Replay ordering policies over the demo shops' last 16 weeks: stock-outs, lost sales and cash tied up in stock.

    .venv\\Scripts\\python.exe backend\\scripts\\simulate_policies.py [--weeks 16]

Every policy starts the window with the same stock (2 weeks of normal sales per product), faces the same customers
(each day's actual sales) and orders once a week; orders arrive after the product's lead time. Unmet demand is a
lost sale. Forecasting models are trained only on days before the window, so nothing is seen in advance.

Policies:
  Shopkeeper rule      reorder when stock + on order is under 1 week of recent sales; order 2 weeks' worth.
  App today            the app's reorder engine at 95% service; forest errors measured with the forest trained on
                       all days so far, i.e. on days it has already seen (how the app sizes safety stock now).
  App, honest errors   the same, but the errors come from a forest that had NOT seen those days.
  App + ABC            honest errors, and a service level per product: 98% for the products bringing in the top
                       80% of sales (A), 95% for the next 15% (B), 90% for the rest (C).

Reads the demo SQLite database; writes nothing to it. The report goes to docs/32_policy_simulation.md.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'data' / 'demo' / 'demo.db').as_posix()}"
os.environ["MODEL_DIR"] = str(ROOT / "data" / "demo" / "models")
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session, joinedload  # noqa: E402

from app.db.session import get_engine  # noqa: E402
from app.db.tenancy import SHOP_KEY  # noqa: E402
from app.models import DailySales, Product, Shop  # noqa: E402
from app.services.forecast_engine import load_context  # noqa: E402
from app.services.forecasting import choose_auto  # noqa: E402
from app.services.recommendations import policy_settings  # noqa: E402
from ml.features.build import MIN_HISTORY_DAYS, build_rows  # noqa: E402
from ml.inventory import formulas as f  # noqa: E402
from ml.inventory.recommend import ItemState, recommend  # noqa: E402
from ml.inventory.simulate import Outcome, replay  # noqa: E402
from ml.models.baselines import moving_average  # noqa: E402
from ml.models.forest import fit_forest, predict, training_rows  # noqa: E402

REVIEW = 7
ERROR_ORIGINS = 8                 # weekly past periods used to measure forecast errors (the app uses up to 16)
HORIZON = 28
ABC_LEVELS = {"A": 0.98, "B": 0.95, "C": 0.90}
REPORT = ROOT / "docs" / "32_policy_simulation.md"


def train_forest(panel, last_target: int):
    origins = list(range(MIN_HISTORY_DAYS + 1, last_target - HORIZON + 2, REVIEW))
    return fit_forest(training_rows(build_rows(panel, origins, HORIZON), last_target))


def forecast(model, panel, origin: int, slow: np.ndarray) -> np.ndarray:
    """Forest for most products, the 28-day moving average for the patterns Auto gives to it (as the app does)."""
    n = len(panel.item_ids)
    rf = np.clip(predict(model, build_rows(panel, [origin], HORIZON)).reshape(n, HORIZON), 0, None)
    ma = moving_average(panel.sales[:, : origin - 1], HORIZON, 28)
    return np.nan_to_num(np.where(slow[:, None], ma, rf))


def error_sigmas(model, panel, t0: int, protection: np.ndarray, slow: np.ndarray):
    """(period sigma, daily sigma) per item from the ERROR_ORIGINS weekly periods that end before day t0."""
    p_max = int(protection.max())
    starts = [t0 - p_max - REVIEW * k for k in range(ERROR_ORIGINS)]
    n = len(panel.item_ids)
    period, daily = [[] for _ in range(n)], [[] for _ in range(n)]
    for s in starts:
        fc = forecast(model, panel, s, slow)
        for i in range(n):
            p = int(protection[i])
            a, fi = panel.sales[i, s - 1: s - 1 + p], fc[i, :p]
            known = ~np.isnan(a)
            daily[i].extend((fi[known] - a[known]).tolist())
            if known.all():
                period[i].append(float(fi.sum() - a.sum()))
    return ([f.period_sigma_from_errors(np.array(e)) for e in period],
            [float(np.sqrt(np.mean(np.square(e)))) if len(e) >= 14 else None for e in daily])


def abc_classes(revenue: np.ndarray) -> np.ndarray:
    order = np.argsort(-revenue)
    share = np.cumsum(revenue[order]) / max(revenue.sum(), 1e-9)
    cls = np.empty(len(revenue), dtype=object)
    for rank, i in enumerate(order):
        before = share[rank - 1] if rank else 0.0      # share of sales from products ranked above this one
        cls[i] = "A" if before < 0.80 else "B" if before < 0.95 else "C"
    return cls


def run_shop(db: Session, weeks: int, ordering_cost: float | None = None) -> tuple[dict[str, Outcome], dict]:
    last = db.scalar(select(DailySales.sales_date).order_by(DailySales.sales_date.desc()).limit(1))
    ctx = load_context(db, through=last + timedelta(days=HORIZON))   # room for forecasts made near the end
    panel, n_days = ctx.panel, ctx.d_num(last)
    days = weeks * 7
    t0 = n_days - days + 1                                   # first simulated day (d_num)
    products = {p.id: p for p in db.scalars(select(Product).options(joinedload(Product.supplier)))}
    items = [products[int(pid)] for pid in ctx.product_ids]
    lead = np.array([p.effective_lead_time_days or 3 for p in items])
    protection = lead + REVIEW
    price = np.array([float(p.unit_price or 0) for p in items])
    cost = np.array([float(p.unit_cost or 0) for p in items])
    by_class = choose_auto(db)["by_class"]
    slow = np.array([(p.demand_class or "unknown") in by_class for p in items])
    policy = policy_settings(db, {"ordering_cost": ordering_cost})

    # Two forests, neither trained on the window: A has not seen the error periods either (honest errors);
    # B is trained up to the window, like the app's own model (its errors on those periods are in-sample).
    forest_a = train_forest(panel, t0 - 1 - ERROR_ORIGINS * REVIEW - int(protection.max()))
    forest_b = train_forest(panel, t0 - 1)
    honest = error_sigmas(forest_a, panel, t0, protection, slow)
    in_sample = error_sigmas(forest_b, panel, t0, protection, slow)
    forecasts = {t: forecast(forest_b, panel, t0 + t, slow) for t in range(0, days, REVIEW)}

    before = panel.sales[:, t0 - 1 - 91: t0 - 1]
    revenue = np.nansum(before, axis=1) * price
    abc = abc_classes(revenue)
    recent = np.nan_to_num(np.nanmean(panel.sales[:, t0 - 1 - 28: t0 - 1], axis=1))
    start = np.ceil(recent * 14)

    def engine(sigmas, levels=None, **changes):
        period_sigma, daily_sigma = sigmas

        def decide(t, on_hand, on_order):
            qty = np.zeros(len(items))
            for i, p in enumerate(items):
                sl = levels[abc[i]] if levels else policy.service_level
                state = ItemState(sku=p.sku, name=p.name, on_hand=on_hand[i], on_order=on_order[i],
                                  lead_time_days=int(lead[i]), unit_cost=cost[i] or None,
                                  min_order_qty=p.min_order_qty, pack_size=p.pack_size, demand_class=p.demand_class)
                rec = recommend(state, forecasts[t][i], daily_sigma[i], replace(policy, **{"service_level": sl, **changes}),
                                period_sigma=period_sigma[i])
                qty[i] = rec.suggested_qty
            return qty
        return decide

    def shopkeeper(t, on_hand, on_order):
        avg = np.nan_to_num(np.nanmean(panel.sales[:, t0 - 1 + t - 28: t0 - 1 + t], axis=1))
        qty = np.zeros(len(items))
        for i, p in enumerate(items):
            if on_hand[i] + on_order[i] < avg[i] * 7:
                qty[i] = f.order_quantity(on_hand[i] + on_order[i], on_hand[i] + on_order[i] + avg[i] * 14,
                                          p.min_order_qty, p.pack_size)
        return qty

    demand = panel.sales[:, t0 - 1: t0 - 1 + days]
    policies = {
        "Shopkeeper rule": shopkeeper,
        "App today (95%)": engine(in_sample),
        "App, honest errors (95%)": engine(honest),
        "App + ABC (98/95/90%)": engine(honest, ABC_LEVELS),
        "App, orders of at most 2 weeks": engine(in_sample, max_cycle_days=14),
        "App, orders of at most 10 days": engine(in_sample, max_cycle_days=10),
        "App at 90% service": engine(in_sample, service_level=0.90),
    }
    outcomes = {name: replay(demand, start, lead, REVIEW, decide) for name, decide in policies.items()}
    info = {"start": ctx.date_of(t0), "end": ctx.date_of(n_days), "items": len(items), "price": price, "cost": cost,
            "ordering_cost": policy.ordering_cost, "holding_rate": policy.holding_cost_rate,
            "abc": {k: int((abc == k).sum()) for k in "ABC"},
            "sigma_ratio": _ratio(honest[0], in_sample[0])}
    return outcomes, info


def _ratio(honest, in_sample) -> float | None:
    pairs = [(h, s) for h, s in zip(honest, in_sample) if h is not None and s is not None and s > 0]
    return float(np.median([h / s for h, s in pairs])) if pairs else None


def headline(outcomes: dict[str, Outcome], info: dict) -> str:
    """One sentence: the app as it is today against the shopkeeper rule."""
    def numbers(o: Outcome):
        stock = float((o.stock_units_days / o.days * info["cost"]).sum())
        margin = np.clip(info["price"] - info["cost"], 0, None)
        total = (stock * info["holding_rate"] * o.days / 365 + o.orders.sum() * info["ordering_cost"]
                 + float((o.lost * margin).sum()))
        return float(o.stockout_days.sum()), float((o.lost * info["price"]).sum()), stock, total
    shop, app = numbers(outcomes["Shopkeeper rule"]), numbers(outcomes["App today (95%)"])
    change = [(a - s) / s if s else 0.0 for s, a in zip(shop, app)]
    return (f"Compared with the shopkeeper rule, the app as it is today had {-change[0]:.0%} fewer stock-out days and "
            f"{-change[1]:.0%} less lost sales, held {change[2]:.0%} more stock by value, and cost "
            f"{-change[3]:.0%} less in total.")


def table(outcomes: dict[str, Outcome], info: dict) -> list[str]:
    """One row per policy. Total cost uses the app's own cost settings: a fixed cost per order line, a yearly
    holding cost as a share of stock value, and the profit lost on sales that could not be made."""
    price, cost = info["price"], info["cost"]
    margin = np.clip(price - cost, 0, None)
    lines = ["| Policy | Customers served | Stock-out days | Lost sales (Rs) | Average stock (Rs) | Orders | "
             "Total cost (Rs) |", "|---|---|---|---|---|---|---|"]
    rows = []
    for name, o in outcomes.items():
        stock = float((o.stock_units_days / o.days * cost).sum())
        total = (stock * info["holding_rate"] * o.days / 365 + o.orders.sum() * info["ordering_cost"]
                 + float((o.lost * margin).sum()))
        rows.append((name, o, stock, total))
    best = min(rows, key=lambda r: r[3])[0]
    for name, o, stock, total in rows:
        fill = o.sold.sum() / max(o.demand.sum(), 1e-9)
        cells = [f"{fill:.1%}", f"{int(o.stockout_days.sum()):,}", f"{float((o.lost * price).sum()):,.0f}",
                 f"{stock:,.0f}", f"{int(o.orders.sum()):,}", f"{total:,.0f}"]
        if name == best:
            cells[-1] = f"**{cells[-1]}**"
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--weeks", type=int, default=16)
    parser.add_argument("--ordering-cost", type=float, default=None,
                        help="cost per order line in Rs (default: the shop's setting); changes order sizes and costs")
    args = parser.parse_args()
    started = time.time()
    engine = get_engine()
    with Session(engine) as plain:
        shops = plain.execute(select(Shop.id, Shop.name)).all()
    report = ["# Ordering policy simulation", "",
              f"What each ordering policy would have done over the last {args.weeks} weeks of the demo shops "
              "(synthetic data). Same starting stock, same customers (each day's actual sales), weekly ordering, "
              "orders arrive after each product's lead time, unmet demand is lost. Forecasting models were trained "
              "only on days before the window. Stock-out days count product-days on which some customers left "
              "without the product. Average stock is valued at cost. Total cost = holding cost of the average stock + a fixed cost "
              "per order line + profit lost on missed sales, using the app's cost settings (25% a year to hold stock, "
              f"{'Rs %g' % args.ordering_cost if args.ordering_cost else 'the shop setting, Rs 200,'} per order line); "
              "the cheapest policy is in bold.", "",
              "Generated by `backend/scripts/simulate_policies.py`; policies are described there.", ""]
    for shop_id, name in shops:
        with Session(engine, info={SHOP_KEY: shop_id}) as db:
            span = db.execute(select(DailySales.sales_date).order_by(DailySales.sales_date)).scalars().all()
            if not span or (span[-1] - span[0]).days + 1 < MIN_HISTORY_DAYS + 7 * args.weeks + 200:
                print(f"shop {shop_id} skipped: not enough history")
                continue
            outcomes, info = run_shop(db, args.weeks, args.ordering_cost)
        ratio = info["sigma_ratio"]
        report += [f"## {name}", "",
                   f"{info['start']} to {info['end']}, {info['items']} products (A {info['abc']['A']}, "
                   f"B {info['abc']['B']}, C {info['abc']['C']}).",
                   *([f"Measured honestly, forecast errors are {ratio:.2f}x the size the app measures today "
                      "(median over products)."] if ratio else []), "",
                   *table(outcomes, info), "", headline(outcomes, info), ""]
        print(f"shop {shop_id} done ({time.time() - started:.0f}s)")
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
