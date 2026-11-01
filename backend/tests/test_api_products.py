"""Product API tests. The `client` fixture (conftest.py) is logged in as a manager
on an isolated in-memory database."""

from __future__ import annotations

import pytest


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok", "database": "ok"}


def test_list_paginates(client):
    body = client.get("/api/v1/products", params={"page_size": 2}).json()
    assert body["total"] == 3 and body["pages"] == 2 and len(body["items"]) == 2
    assert client.get("/api/v1/products", params={"page": 2, "page_size": 2}).json()["items"][0]["sku"] == "HOBBIES_1_001"


def test_list_filters_search_and_sort(client):
    get = lambda **p: client.get("/api/v1/products", params=p).json()  # noqa: E731
    assert [i["sku"] for i in get(category="foods")["items"]] == ["FOODS_1_001", "FOODS_1_002"]
    assert get(search="hobbies")["total"] == 1
    assert get(demand_class="intermittent")["items"][0]["on_hand"] == 0
    assert [i["sku"] for i in get(sort="unit_price", order="desc")["items"]][0] == "HOBBIES_1_001"
    assert [i["on_hand"] for i in get(sort="on_hand")["items"]] == [0, 5, 10]


def test_invalid_query_rejected(client):
    assert client.get("/api/v1/products", params={"page_size": 500}).status_code == 422
    assert client.get("/api/v1/products", params={"sort": "password"}).status_code == 422


def test_get_product_and_404(client):
    body = client.get("/api/v1/products/1").json()
    assert body["category"]["code"] == "FOODS"
    assert body["effective_lead_time_days"] == 3          # from supplier
    assert client.get("/api/v1/products/999").json() == {"detail": "Product 999 not found"}


def test_create_product_normalises_sku_and_starts_with_zero_stock(client):
    response = client.post("/api/v1/products", json={
        "sku": " household_2_100 ", "name": "New item", "category_code": "foods",
        "supplier_id": 1, "unit_price": "4.20", "pack_size": 6, "min_order_qty": 6})
    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "HOUSEHOLD_2_100" and body["on_hand"] == 0 and body["unit_price"] == "4.20"


def test_duplicate_sku_is_409(client):
    payload = {"sku": "foods_1_001", "name": "Dup", "category_code": "FOODS", "unit_price": "1.00"}
    response = client.post("/api/v1/products", json=payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.parametrize("change", [
    {"unit_price": "-1"}, {"pack_size": 0}, {"sku": "bad sku!"}, {"name": "   "}, {"unit_price": "1.234"},
    {"lead_time_days": 0},
])
def test_invalid_product_input_is_422(client, change):
    payload = {"sku": "NEW_1", "name": "Ok", "category_code": "FOODS", "unit_price": "1.00", **change}
    assert client.post("/api/v1/products", json=payload).status_code == 422


def test_unknown_references_are_422(client):
    base = {"sku": "NEW_2", "name": "Ok", "unit_price": "1.00"}
    assert client.post("/api/v1/products", json={**base, "category_code": "TOYS"}).status_code == 422
    assert client.post("/api/v1/products",
                       json={**base, "category_code": "FOODS", "supplier_id": 42}).status_code == 422


def test_update_product(client):
    response = client.patch("/api/v1/products/2", json={"lead_time_days": 10, "is_active": False})
    assert response.status_code == 200
    body = response.json()
    assert body["effective_lead_time_days"] == 10 and body["is_active"] is False
    assert body["sku"] == "FOODS_1_002"                     # untouched fields unchanged
    assert client.patch("/api/v1/products/2", json={"sku": "CHANGED"}).json()["sku"] == "FOODS_1_002"


def test_sales_history_defaults_to_last_90_days(client):
    body = client.get("/api/v1/products/1/sales").json()
    assert body["end"] == "2016-04-09" and body["start"] == "2016-01-11"
    assert len(body["points"]) == 90
    ranged = client.get("/api/v1/products/1/sales", params={"start": "2016-01-01", "end": "2016-01-03"}).json()
    assert [p["units"] for p in ranged["points"]] == [0, 1, 2] and ranged["total_units"] == 3
    assert client.get("/api/v1/products/1/sales", params={"start": "2016-02-01", "end": "2016-01-01"}).status_code == 422


def test_reference_lists(client):
    assert [c["code"] for c in client.get("/api/v1/categories").json()] == ["FOODS", "HOBBIES"]
    assert client.get("/api/v1/suppliers").json()[0]["lead_time_days"] == 3
