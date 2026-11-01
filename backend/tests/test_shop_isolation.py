"""Multi-shop isolation: a shop's users can never see, change or use another shop's data.

Shop A is the shared test shop (conftest: products 1-3, supplier 1, sales for product 1).
Shop B is added here with the SAME SKU and supplier code as shop A, so any mix-up shows.
For every endpoint, shop B's users get only shop B's rows, and shop A's ids give 404.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.tenancy import ShopNotSet, all_shops, use_shop
from app.models import (
    CalendarDay, Category, DailySales, InventoryBalance, Product, PurchaseOrder, Shop, Supplier, User,
)
from app.models.enums import UserRole
from tests.conftest import TEST_PASSWORD, login

B_USERS = {"admin": "admin@shop-b.test", "manager": "manager@shop-b.test", "viewer": "viewer@shop-b.test"}


def login_b(api, role: str) -> dict[str, str]:
    response = api.post("/api/v1/auth/login", data={"username": B_USERS[role], "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def shops(api):
    """Shop A with a forecast, recommendations and a purchase order; shop B with its own small catalogue."""
    # More history for shop A's product 1, so a recommendation run has something to work on.
    with api.app.state.make_session() as s:
        first = date(2016, 1, 1)
        days = [first - timedelta(days=k) for k in range(1, 101)]
        s.add_all([CalendarDay(day=d) for d in days])
        s.flush()
        s.add_all([DailySales(product_id=1, sales_date=d, units=(-k) % 3) for k, d in enumerate(days, start=1)])
        s.commit()

    with api.app.state.plain_session() as s:
        shop = Shop(name="Shop B")
        s.add(shop)
        s.flush()
        use_shop(s, shop.id)
        for role, email in B_USERS.items():
            s.add(User(email=email, full_name=f"B {role}", role=UserRole(role),
                       hashed_password=hash_password(TEST_PASSWORD, iterations=1_000)))
        foods = Category(code="FOODS", name="Foods")
        supplier = Supplier(code="SUP_A", name="B's supplier", lead_time_days=2)
        s.add_all([foods, supplier])
        s.flush()
        for sku in ("FOODS_1_001", "B_ONLY_1"):                     # FOODS_1_001 also exists in shop A
            product = Product(sku=sku, name=f"B {sku}", category=foods, supplier=supplier,
                              unit_price=Decimal("50.00"), unit_cost=Decimal("40.00"))
            s.add(product)
            s.flush()
            s.add(InventoryBalance(product_id=product.id, on_hand=7))
        s.commit()
        b = {"shop_id": shop.id, "supplier_id": supplier.id,
             "product_ids": list(s.scalars(select(Product.id).order_by(Product.id)))}

    a = login(api, "manager")
    forecast = api.post("/api/v1/forecasts/runs", json={"model_name": "moving_avg_28"}, headers=a).json()
    rec_run = api.post("/api/v1/recommendations/runs", json={}, headers=a).json()
    recs = api.get("/api/v1/recommendations", params={"run_id": rec_run["id"]}, headers=a).json()
    assert "items" in recs, (forecast, rec_run, recs)
    po = api.post("/api/v1/purchase-orders", json={"supplier_id": 1, "lines": [{"product_id": 1, "quantity": 12}]},
                  headers=a).json()
    adjusted = api.post("/api/v1/inventory/adjustments", headers=a,
                        json={"product_id": 1, "quantity": 3, "txn_type": "adjustment", "reason": "count"})
    assert adjusted.status_code == 201, adjusted.text
    a_ids = {"product": 1, "supplier": 1, "forecast_run": forecast["id"], "rec_run": rec_run["id"],
             "recommendation": recs["items"][0]["id"], "po": po["id"], "po_line": po["lines"][0]["id"],
             "user": 1}
    return {"a": a, "a_ids": a_ids, "b": b, "b_manager": login_b(api, "manager"), "b_admin": login_b(api, "admin")}


def test_login_tells_the_user_their_shop(api, shops):
    me_a = api.get("/api/v1/auth/me", headers=shops["a"]).json()
    me_b = api.get("/api/v1/auth/me", headers=shops["b_manager"]).json()
    assert me_a["shop"] == {"id": 1, "name": "Test shop", "is_demo": False}
    assert me_b["shop"]["name"] == "Shop B" and me_b["shop"]["id"] == shops["b"]["shop_id"]


def test_lists_only_show_the_users_own_shop(api, shops):
    b, h = shops["b"], shops["b_manager"]
    products = api.get("/api/v1/products", headers=h).json()
    assert sorted(p["id"] for p in products["items"]) == b["product_ids"]
    assert {p["sku"] for p in products["items"]} == {"FOODS_1_001", "B_ONLY_1"}
    assert [s["id"] for s in api.get("/api/v1/suppliers", headers=h).json()] == [b["supplier_id"]]
    assert len(api.get("/api/v1/categories", headers=h).json()) == 1
    inventory = api.get("/api/v1/inventory", headers=h).json()
    assert sorted(r["product_id"] for r in inventory["items"]) == b["product_ids"]
    assert api.get("/api/v1/inventory/transactions", headers=h).json()["items"] == []
    assert api.get("/api/v1/purchase-orders", headers=h).json()["items"] == []
    assert api.get("/api/v1/forecasts/runs", headers=h).json() == []
    assert api.get("/api/v1/recommendations/runs", headers=h).json() == []
    assert api.get("/api/v1/imports/jobs", headers=h).json() == []
    assert {u["email"] for u in api.get("/api/v1/users", headers=shops["b_admin"]).json()} == set(B_USERS.values())

    summary = api.get("/api/v1/dashboard/summary", headers=h).json()
    assert summary["active_products"] == 2 and summary["units_on_hand"] == 14
    assert summary["sales"] is None and summary["forecast"] is None and summary["recent_activity"] == []
    assert api.get("/api/v1/analytics/sales-trend", headers=h).json() == []


def test_shop_a_ids_are_not_found_from_shop_b(api, shops):
    ids, h = shops["a_ids"], shops["b_manager"]
    for path in [f"/api/v1/products/{ids['product']}", f"/api/v1/products/{ids['product']}/sales",
                 f"/api/v1/inventory/{ids['product']}", f"/api/v1/forecasts/runs/{ids['forecast_run']}",
                 f"/api/v1/recommendations/runs/{ids['rec_run']}", f"/api/v1/purchase-orders/{ids['po']}"]:
        assert api.get(path, headers=h).status_code == 404, path
    assert api.get(f"/api/v1/forecasts/products/{ids['product']}",
                   params={"run_id": ids["forecast_run"]}, headers=h).status_code == 404
    assert api.get("/api/v1/recommendations", params={"run_id": ids["rec_run"]}, headers=h).status_code == 404


def test_shop_b_cannot_change_or_use_shop_a_data(api, shops):
    ids, h = shops["a_ids"], shops["b_manager"]
    assert api.patch(f"/api/v1/products/{ids['product']}", json={"name": "Hacked"}, headers=h).status_code == 404
    adjust = api.post("/api/v1/inventory/adjustments", headers=h,
                      json={"product_id": ids["product"], "quantity": -5, "txn_type": "adjustment", "reason": "stock count"})
    assert adjust.status_code == 404
    assert api.patch(f"/api/v1/recommendations/{ids['recommendation']}", json={"review_status": "approved"},
                     headers=h).status_code == 404
    for action in ("submit", "cancel"):
        assert api.post(f"/api/v1/purchase-orders/{ids['po']}/{action}", headers=h).status_code == 404
    receive = api.post(f"/api/v1/purchase-orders/{ids['po']}/receive", headers=h,
                       json={"lines": [{"item_id": ids["po_line"], "quantity": 1}]})
    assert receive.status_code == 404
    assert api.patch(f"/api/v1/users/{ids['user']}", json={"is_active": False},
                     headers=shops["b_admin"]).status_code == 404

    # Orders cannot point at shop A's supplier or products.
    order = {"supplier_id": ids["supplier"], "lines": [{"product_id": shops["b"]["product_ids"][0], "quantity": 1}]}
    assert api.post("/api/v1/purchase-orders", json=order, headers=h).status_code in (404, 422)
    order = {"supplier_id": shops["b"]["supplier_id"], "lines": [{"product_id": ids["product"], "quantity": 1}]}
    assert api.post("/api/v1/purchase-orders", json=order, headers=h).status_code in (404, 422)
    assert api.post("/api/v1/purchase-orders/from-recommendations", headers=h,
                    json={"recommendation_ids": [ids["recommendation"]]}).status_code in (404, 409, 422)
    assert api.post("/api/v1/recommendations/runs", json={"forecast_run_id": ids["forecast_run"]},
                    headers=h).status_code == 404

    # Shop A is exactly as it was.
    a = shops["a"]
    assert api.get(f"/api/v1/products/{ids['product']}", headers=a).json()["name"] == "Item 0"
    assert api.get(f"/api/v1/inventory/{ids['product']}", headers=a).json()["on_hand"] == 13
    assert api.get(f"/api/v1/purchase-orders/{ids['po']}", headers=a).json()["status"] == "draft"


def test_same_codes_and_numbers_are_separate_per_shop(api, shops):
    h = shops["b_manager"]
    created = api.post("/api/v1/products", headers=h, json={
        "sku": "HOBBIES_1_001", "name": "B hobby", "category_code": "FOODS", "unit_price": "10.00"})
    assert created.status_code == 201, created.text                   # SKU exists in shop A: fine in shop B
    assert api.post("/api/v1/products", headers=h, json={
        "sku": "B_ONLY_1", "name": "Dup", "category_code": "FOODS", "unit_price": "1.00"}).status_code == 409

    po = api.post("/api/v1/purchase-orders", headers=h, json={
        "supplier_id": shops["b"]["supplier_id"], "lines": [{"product_id": shops["b"]["product_ids"][0], "quantity": 2}]})
    assert po.status_code == 201 and po.json()["po_number"] == "PO-000001"          # numbering is per shop

    # Emails decide the shop at login, so they stay unique across shops.
    taken = api.post("/api/v1/users", headers=shops["b_admin"], json={
        "email": "manager@test.local", "full_name": "Copy", "password": "another-password-1", "role": "viewer"})
    assert taken.status_code == 409


def test_import_and_forecast_use_only_the_shops_own_products(api, shops):
    h = shops["b_manager"]
    csv = "sku,date,units\nB_ONLY_1,2016-04-01,3\nHOBBIES_1_001,2016-04-01,1\n"   # second SKU is shop A's only
    preview = api.post("/api/v1/imports/sales/preview", headers=h,
                       files={"file": ("sales.csv", csv.encode(), "text/csv")}).json()
    assert preview["can_import"] is False and "Unknown SKU 'HOBBIES_1_001'" in preview["errors"][0]["message"]

    run = api.post("/api/v1/forecasts/runs", json={"model_name": "moving_avg_28"}, headers=h)
    assert run.status_code == 400 and "No sales history" in run.json()["detail"]        # shop A's sales unseen

    for dataset in ("products", "inventory", "transactions"):
        text = api.get(f"/api/v1/exports/{dataset}.csv", headers=h).text
        assert "Item 0" not in text and "Supplier A" not in text, dataset


def test_a_session_without_a_shop_is_refused(db):
    with Session(db.get_bind()) as bare:
        with pytest.raises(ShopNotSet):
            bare.scalars(select(Product)).all()
        with pytest.raises(ShopNotSet):
            bare.add(Category(code="X", name="X"))
            bare.flush()
        bare.rollback()
        with all_shops(bare):
            assert bare.scalars(select(Shop)).all()                     # explicit opt-in still works


def test_adding_a_row_for_another_shop_is_refused(db):
    other = Shop(name="Other")
    db.add(other)
    db.flush()
    db.add(Category(code="X", name="X", shop_id=other.id))
    with pytest.raises(ShopNotSet):
        db.flush()
    db.rollback()
    assert db.scalar(select(PurchaseOrder)) is None
