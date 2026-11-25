"""Shelves: where products are kept, so staff can find them. Test data (conftest.py): products 1-3 in the test shop."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import Product, Shelf
from app.services import demo_shop
from tests.conftest import login
from tests.test_imports import new_shop, send, xlsx  # noqa: F401  (new_shop is a fixture)


def add_shelf(client, code="a-1", name="Aisle A, top shelf", area="Front shop"):
    return client.post("/api/v1/shelves", json={"code": code, "name": name, "area": area})


def test_shelves_can_be_added_listed_and_changed(client):
    created = add_shelf(client)
    assert created.status_code == 201, created.text
    shelf = created.json()
    assert shelf["code"] == "A-1" and shelf["area"] == "Front shop" and shelf["product_count"] == 0
    assert add_shelf(client, code="A-1").status_code == 409                       # codes are unique in the shop

    other = add_shelf(client, code="STORE", name="Back storeroom", area="  ").json()
    assert other["area"] is None                                                   # blank area is stored as none
    changed = client.patch(f"/api/v1/shelves/{shelf['id']}", json={"name": "Aisle A, rice", "area": None}).json()
    assert changed["name"] == "Aisle A, rice" and changed["area"] is None and changed["code"] == "A-1"
    assert client.patch(f"/api/v1/shelves/{shelf['id']}", json={"code": "store"}).status_code == 409
    assert [s["code"] for s in client.get("/api/v1/shelves").json()] == ["A-1", "STORE"]


def test_products_get_a_shelf_and_can_be_found_by_it(client):
    shelf = add_shelf(client).json()
    product = client.patch("/api/v1/products/1", json={"shelf_id": shelf["id"]})
    assert product.status_code == 200 and product.json()["shelf"]["code"] == "A-1"
    assert client.patch("/api/v1/products/2", json={"shelf_id": 999}).status_code == 422   # unknown shelf

    on_shelf = client.get("/api/v1/products", params={"shelf_id": shelf["id"]}).json()
    assert [p["id"] for p in on_shelf["items"]] == [1]
    no_shelf = client.get("/api/v1/products", params={"shelf_id": 0}).json()
    assert {p["id"] for p in no_shelf["items"]} == {2, 3}
    assert client.get("/api/v1/shelves").json()[0]["product_count"] == 1
    by_shelf = client.get("/api/v1/products", params={"sort": "shelf", "order": "desc"}).json()["items"]
    assert by_shelf[-1]["id"] == 1 or by_shelf[0]["id"] == 1                       # sorting by shelf works

    assert client.delete(f"/api/v1/shelves/{shelf['id']}").status_code == 204       # products stay, without a shelf
    assert client.get("/api/v1/products/1").json()["shelf"] is None


def test_viewers_can_look_but_not_change_shelves(api, client):
    shelf = add_shelf(client).json()
    viewer = login(api, "viewer")
    assert api.get("/api/v1/shelves", headers=viewer).status_code == 200
    assert api.post("/api/v1/shelves", json={"code": "X", "name": "X"}, headers=viewer).status_code == 403
    assert api.patch(f"/api/v1/shelves/{shelf['id']}", json={"name": "Y"}, headers=viewer).status_code == 403
    assert api.delete(f"/api/v1/shelves/{shelf['id']}", headers=viewer).status_code == 403


def test_purchase_order_lines_say_where_to_put_the_delivery(client):
    shelf = add_shelf(client).json()
    client.patch("/api/v1/products/1", json={"shelf_id": shelf["id"]})
    po = client.post("/api/v1/purchase-orders", json={"supplier_id": 1, "lines": [{"product_id": 1, "quantity": 5}]})
    assert po.status_code == 201, po.text
    line = po.json()["lines"][0]
    assert line["shelf_code"] == "A-1" and line["shelf_name"] == "Aisle A, top shelf"


def test_product_import_sets_shelves_and_creates_new_ones(api, new_shop):  # noqa: F811
    h = new_shop
    rows = [["sku", "name", "category", "unit_price", "shelf"],
            ["RICE-5KG", "Rice 5 kg", "Grains", 780, "a-1"],
            ["SALT-1KG", "Salt 1 kg", "Grains", 30, ""]]
    job = send(api, h, "products", xlsx(rows))
    assert job.status_code == 201, job.text
    assert job.json()["errors"]["shelves_added"] == 1                            # the job result (stored in "errors")
    products = {p["sku"]: p for p in api.get("/api/v1/products", headers=h).json()["items"]}
    assert products["RICE-5KG"]["shelf"]["code"] == "A-1" and products["SALT-1KG"]["shelf"] is None

    rows[1][4] = ""                                                             # an empty cell keeps the shelf
    send(api, h, "products", xlsx(rows))
    rice = api.get("/api/v1/products", headers=h, params={"search": "RICE"}).json()["items"][0]
    assert rice["shelf"]["code"] == "A-1"


def test_demo_shops_get_a_shelf_for_every_category(db):
    from datetime import date
    data = demo_shop.generate(date(2026, 10, 31), days=120)
    demo_shop.load(db, data)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Shelf)) == len(demo_shop.SHELVES) + 1     # + storeroom
    assert db.scalar(select(func.count()).select_from(Product).where(Product.shelf_id.is_(None))) == 0
    assert demo_shop.add_shelves(db) == 0                                       # running it again changes nothing
