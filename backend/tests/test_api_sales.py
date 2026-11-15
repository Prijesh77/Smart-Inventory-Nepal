"""Daily sales entry API tests. Test data (conftest.py):
  product 1 FOODS_1_001: 10 on hand, price 2.50
  product 2 FOODS_1_002: 0 on hand, price 1.00
  product 3 HOBBIES_1_001: 5 on hand, price 9.99
Seeded sales are in 2016, so "today" starts with nothing recorded.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models import DailySales, Product
from tests.conftest import login

TODAY = date.today()


def record(client, items, day=TODAY, close_day=False):
    return client.post("/api/v1/sales", json={
        "sales_date": day.isoformat(), "close_day": close_day,
        "items": [{"product_id": p, "units": u} for p, u in items]})


def on_hand(client, product_id):
    return client.get(f"/api/v1/inventory/{product_id}").json()["on_hand"]


def test_recording_sales_adds_to_the_day_and_takes_stock(client):
    response = record(client, [(1, 4), (3, 2)])
    assert response.status_code == 201, response.text
    body = response.json()
    assert [(i["sku"], i["units"], i["on_hand"]) for i in body["items"]] == [("FOODS_1_001", 4, 6), ("HOBBIES_1_001", 2, 3)]
    assert body["total_units"] == 6
    assert Decimal(body["total_amount"]) == Decimal("29.98")          # 4 x 2.50 + 2 x 9.99
    assert on_hand(client, 1) == 6 and on_hand(client, 3) == 3

    history = client.get("/api/v1/inventory/transactions", params={"product_id": 1}).json()["items"]
    assert [(t["txn_type"], t["quantity"], t["balance_after"]) for t in history] == [("sale", -4, 6)]
    assert history[0]["reason"] == f"Sales entry for {TODAY}" and history[0]["created_by_email"] == "manager@test.local"


def test_entries_on_the_same_day_add_up_and_duplicates_are_merged(client):
    assert record(client, [(1, 2), (1, 1)]).json()["items"][0]["units"] == 3
    body = record(client, [(1, 4)]).json()
    assert body["items"][0]["units"] == 7 and body["items"][0]["on_hand"] == 3
    assert client.get("/api/v1/sales").json()["total_units"] == 7      # default date is today


def test_negative_units_correct_a_mistake_and_return_stock(client):
    record(client, [(1, 5)])
    body = record(client, [(1, -2)]).json()
    assert body["items"][0]["units"] == 3 and on_hand(client, 1) == 7
    history = client.get("/api/v1/inventory/transactions", params={"product_id": 1}).json()["items"]
    assert (history[0]["txn_type"], history[0]["quantity"]) == ("adjustment", 2)
    assert history[0]["reason"] == f"Sales correction for {TODAY}"

    too_much = record(client, [(1, -4)])
    assert too_much.status_code == 400 and "only 3 units" in too_much.json()["detail"]
    assert on_hand(client, 1) == 7


def test_selling_more_than_stock_saves_nothing_at_all(client):
    response = record(client, [(3, 1), (1, 11)])                     # product 3 is fine, product 1 is not
    assert response.status_code == 409 and "negative" in response.json()["detail"]
    assert on_hand(client, 1) == 10 and on_hand(client, 3) == 5
    assert client.get("/api/v1/sales").json()["items"] == []


def test_dates_must_be_recent_and_not_in_the_future(client):
    assert record(client, [(1, 1)], day=TODAY + timedelta(days=1)).status_code == 400
    old = record(client, [(1, 1)], day=TODAY - timedelta(days=61))
    assert old.status_code == 400 and "Excel import" in old.json()["detail"]
    assert record(client, [(1, 1)], day=TODAY - timedelta(days=3)).status_code == 201
    assert client.get("/api/v1/sales", params={"date": (TODAY - timedelta(days=3)).isoformat()}).json()["total_units"] == 1


def test_unknown_inactive_and_empty_entries_are_refused(client, api):
    assert record(client, [(999, 1)]).status_code == 404
    assert record(client, []).status_code == 400
    assert record(client, [(1, 0)]).status_code == 400
    with api.app.state.make_session() as s:
        s.get(Product, 3).is_active = False
        s.commit()
    inactive = record(client, [(3, 1)])
    assert inactive.status_code == 400 and "inactive" in inactive.json()["detail"]


def test_closing_the_day_records_zero_for_products_with_no_sales(client, api):
    body = record(client, [(1, 2)], close_day=True).json()
    assert body["zero_rows_added"] == 2 and body["products_recorded"] == 3 and body["active_products"] == 3
    assert [i["sku"] for i in body["items"]] == ["FOODS_1_001"]       # 0-unit rows are not listed
    with api.app.state.make_session() as s:
        rows = {r.product_id: (r.units, r.unit_price) for r in s.query(DailySales).filter_by(sales_date=TODAY)}
    assert rows[2] == (0, Decimal("1.00")) and rows[3][0] == 0
    assert on_hand(client, 3) == 5                                    # closing a day never moves stock

    again = record(client, [], close_day=True)                        # closing twice adds nothing
    assert again.status_code == 201 and again.json()["zero_rows_added"] == 0
    assert record(client, [(3, 1)]).json()["total_units"] == 3        # a late sale still adds to the 0 row


def test_viewers_can_read_but_not_record(api):
    api.headers.update(login(api, "viewer"))
    assert api.get("/api/v1/sales").status_code == 200
    assert record(api, [(1, 1)]).status_code == 403


def test_login_is_required(api):
    assert api.get("/api/v1/sales").status_code == 401
