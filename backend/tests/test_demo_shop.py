"""Synthetic demo shop: generated data, loading, and training the forest on it (no M5 data)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    CalendarDay, Category, DailySales, InventoryBalance, InventoryTransaction, ModelEvaluation, Product, Supplier,
)
from app.services import demo_shop
from app.services.forecast_engine import forecast_matrix, load_context
from app.services.model_training import train_shop_model

END = date(2026, 10, 31)


@pytest.fixture(scope="module")
def data():
    return demo_shop.generate(END)


def test_generation_is_repeatable_and_labelled(data):
    again = demo_shop.generate(END)
    assert again.sales == data.sales and again.opening_stock == data.opening_stock
    assert demo_shop.generate(END, seed=1).sales != data.sales
    assert "synthetic" in demo_shop.DEMO_SHOP_NAME.lower()
    assert all(name.endswith("(demo)") for _, name, _, _ in demo_shop.SUPPLIERS)
    assert data.start == END - timedelta(days=demo_shop.DEFAULT_HISTORY_DAYS - 1)
    assert len({p.sku for p in data.products}) == len(data.products) >= 40


def test_prices_are_rupees_and_costs_below_price(data):
    for p in data.products:
        assert 1 <= data.last_price[p.sku] <= 5000
        assert 0 < data.last_cost[p.sku] < data.last_price[p.sku]
    # Price rises happen on 1 Magh: sugar was cheaper at the start of the history.
    sugar = data.sales["SUGAR-1KG"]
    assert sugar[0][2] < sugar[-1][2] == 115


def test_sales_show_festivals_weekends_and_stockouts(data):
    def mean_units(sku, days):
        rows = [u for d, u, _, a in data.sales[sku] if d in days and a]
        return sum(rows) / len(rows)

    tihar_2025 = {date(2025, 10, 16) + timedelta(days=k) for k in range(8)}
    october_2025 = {date(2025, 8, 1) + timedelta(days=k) for k in range(30)}
    assert mean_units("CANDLE-6", tihar_2025) > 3 * mean_units("CANDLE-6", october_2025)

    saturdays = {d for d, *_ in data.sales["NOODLES-70G"] if d.weekday() == 5}
    tuesdays = {d for d, *_ in data.sales["NOODLES-70G"] if d.weekday() == 1}
    assert mean_units("NOODLES-70G", saturdays) > mean_units("NOODLES-70G", tuesdays)

    dashami = date(2025, 10, 2)
    assert all(not a and u == 0 for rows in data.sales.values() for d, u, _, a in rows if d == dashami)
    assert sum(not a for rows in data.sales.values() for *_, a in rows) > len(data.products)   # out-of-stock days
    slow = [p.sku for p in data.products if p.pattern in ("intermittent", "lumpy")]
    assert all(sum(u == 0 for _, u, _, _ in data.sales[s]) > 100 for s in slow)


def test_load_writes_everything_with_an_audit_trail(db, data):
    counts = demo_shop.load(db, data)
    db.commit()
    assert counts["products"] == db.scalar(select(func.count()).select_from(Product)) == len(data.products)
    assert db.scalar(select(func.count()).select_from(Supplier)) == len(demo_shop.SUPPLIERS)
    assert db.scalar(select(func.count()).select_from(Category)) == len(demo_shop.CATEGORIES)
    assert db.scalar(select(func.count()).select_from(DailySales)) == len(data.products) * len(data.sales["SALT-1KG"])
    assert db.scalar(select(func.max(CalendarDay.day))) == END + timedelta(days=demo_shop.CALENDAR_DAYS_AHEAD)
    assert db.get(CalendarDay, date(2026, 11, 8)).event_name.startswith("Laxmi Puja")

    for balance in db.scalars(select(InventoryBalance)):
        audit = db.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity), 0))
                          .where(InventoryTransaction.product_id == balance.product_id))
        assert audit == balance.on_hand
    rice = db.scalar(select(Product).where(Product.sku == "RICE-MANSULI-25KG"))
    assert str(rice.unit_price) == "2150.00" and rice.supplier.lead_time_days == 3


def test_forest_trains_on_the_shop_and_forecasts(db, empty_model_folder):
    short = demo_shop.generate(END, days=240)              # just enough history, keeps the test fast
    shop_id = demo_shop.load(db, short)["shop_id"]
    db.commit()
    summary = train_shop_model(db)
    path = empty_model_folder / f"shop_{shop_id}_random_forest.joblib"
    assert path.exists() and path.with_suffix(".json").exists()
    assert summary["items"] == len(short.products) and summary["training_rows"] > 10_000
    assert 0 < summary["wape_28d_random_forest"] < 1.5

    names = set(db.scalars(select(ModelEvaluation.model_name)))
    assert names == {"random_forest_v1", "moving_avg_28"}
    assert db.scalar(select(func.count()).select_from(ModelEvaluation)
                     .where(ModelEvaluation.demand_class == "all")) == 6        # 2 models x 3 horizons

    ctx = load_context(db, through=END + timedelta(days=28))
    values = forecast_matrix(ctx, "random_forest_v1", END + timedelta(days=1), 28)
    assert values.shape == (len(short.products), 28) and (values >= 0).all()


def test_training_refuses_short_history(db):
    demo_shop.load(db, demo_shop.generate(END, days=120))
    db.commit()
    with pytest.raises(Exception, match="at least"):
        train_shop_model(db)


def test_retrain_from_the_app(api, empty_model_folder):
    """A manager trains the shop's forest from the Forecasting page (no command line)."""
    from tests.conftest import login
    h = login(api, "manager")
    status = api.get("/api/v1/forecasts/model", headers=h).json()
    assert status["trained"] is False and status["can_train"] is False and status["auto_uses"] == "moving_avg_28"
    refused = api.post("/api/v1/forecasts/model/train", headers=h)
    assert refused.status_code == 409 and "7 months" in refused.json()["detail"]
    assert api.post("/api/v1/forecasts/model/train", headers=login(api, "viewer")).status_code == 403

    # Give the test shop a demo shop's 8 months of sales (its own products), then train.
    with api.app.state.make_session() as s:
        shop_id = demo_shop.load(s, demo_shop.generate(END, days=240))["shop_id"]
        from app.models import User
        from app.core.security import hash_password
        s.add(User(email="m@demo.test", full_name="M", role="manager",
                   hashed_password=hash_password("test-password-123", iterations=1_000)))
        s.commit()
    token = api.post("/api/v1/auth/login", data={"username": "m@demo.test", "password": "test-password-123"}).json()
    h = {"Authorization": f"Bearer {token['access_token']}"}
    assert api.get("/api/v1/forecasts/model", headers=h).json()["can_train"] is True
    assert api.post("/api/v1/forecasts/model/train", headers=h).status_code == 202      # runs before the reply returns
    status = api.get("/api/v1/forecasts/model", headers=h).json()
    assert status["trained"] is True and status["training"] is False and status["trained_at"]
    assert (empty_model_folder / f"shop_{shop_id}_random_forest.joblib").exists()
    assert set(status["holdout_wape"]) == {"random_forest_v1", "moving_avg_28"}
    assert status["auto_uses"] in ("random_forest_v1", "moving_avg_28") and "Auto:" in status["auto_reason"]
