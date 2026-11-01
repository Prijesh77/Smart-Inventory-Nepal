"""Inventory API tests. Test data (conftest.py):
  product 1 FOODS_1_001: 10 on hand, sales d % 3 for 100 days, supplier lead time 3 days
  product 2 FOODS_1_002: 0 on hand, no sales
  product 3 HOBBIES_1_001: 5 on hand, no sales
Last 28 days of product 1: 27 units / 28 days = 0.964 per day -> lead-time demand 2.89.
"""

from __future__ import annotations

import pytest

from app.models import InventoryTransaction, PurchaseOrder, PurchaseOrderItem
from app.models.enums import PurchaseOrderStatus
from tests.conftest import login

AVG = 27 / 28


def adjust(client, product_id, quantity, txn_type="adjustment", reason="cycle count"):
    return client.post("/api/v1/inventory/adjustments",
                       json={"product_id": product_id, "quantity": quantity, "txn_type": txn_type, "reason": reason})


def stock(client, product_id):
    return client.get(f"/api/v1/inventory/{product_id}").json()


def test_stock_overview_hand_checked(client):
    item = stock(client, 1)
    assert item["on_hand"] == 10 and item["on_order"] == 0 and item["inventory_position"] == 10
    assert item["avg_daily_sales"] == pytest.approx(AVG)
    assert item["days_of_cover"] == pytest.approx(10 / AVG)
    assert item["lead_time_days"] == 3 and item["stock_status"] == "ok"
    assert stock(client, 2)["stock_status"] == "no_recent_demand"


def test_adjustment_updates_balance_and_writes_audit_record(client):
    response = adjust(client, 1, -4, reason="damaged in storage")
    assert response.status_code == 201
    txn = response.json()
    assert txn["quantity"] == -4 and txn["balance_after"] == 6
    assert txn["reason"] == "damaged in storage" and txn["created_by_email"] == "manager@test.local"
    assert stock(client, 1)["on_hand"] == 6


def test_cannot_go_negative_and_nothing_is_recorded(client):
    response = adjust(client, 1, -11)
    assert response.status_code == 409 and "negative" in response.json()["detail"]
    assert stock(client, 1)["on_hand"] == 10
    history = client.get("/api/v1/inventory/transactions", params={"product_id": 1}).json()
    assert history["total"] == 0


@pytest.mark.parametrize("quantity, txn_type", [(3, "sale"), (-3, "return"), (5, "receipt"), (5, "initial")])
def test_movement_types_enforce_direction_and_manual_types(client, quantity, txn_type):
    assert adjust(client, 1, quantity, txn_type).status_code in (400, 422)


@pytest.mark.parametrize("payload", [
    {"product_id": 1, "quantity": 0, "reason": "zero"},
    {"product_id": 1, "quantity": 2, "reason": ""},
    {"product_id": 1, "quantity": 2},
])
def test_invalid_adjustments(client, payload):
    assert client.post("/api/v1/inventory/adjustments", json=payload).status_code in (400, 422)


def test_unknown_product_is_404(client):
    assert adjust(client, 999, 1).status_code == 404
    assert client.get("/api/v1/inventory/999").status_code == 404


def test_sale_and_return(client):
    assert adjust(client, 1, -2, "sale", "walk-in sale").json()["balance_after"] == 8
    assert adjust(client, 1, 1, "return", "customer return").json()["balance_after"] == 9


def test_viewer_can_read_but_not_adjust(api):
    viewer = login(api, "viewer")
    assert api.get("/api/v1/inventory", headers=viewer).status_code == 200
    response = api.post("/api/v1/inventory/adjustments", headers=viewer,
                        json={"product_id": 1, "quantity": 1, "reason": "test"})
    assert response.status_code == 403


def test_low_and_out_of_stock_alerts(client):
    assert client.get("/api/v1/inventory/alerts").json() == []
    adjust(client, 1, -8)                      # position 2 < 2.89 lead-time demand -> low
    alerts = client.get("/api/v1/inventory/alerts").json()
    assert [(a["sku"], a["stock_status"]) for a in alerts] == [("FOODS_1_001", "low")]
    adjust(client, 1, -2)                      # nothing left -> out of stock
    assert client.get("/api/v1/inventory/alerts").json()[0]["stock_status"] == "out_of_stock"


def test_on_order_counts_only_open_purchase_orders(api, client):
    with api.app.state.make_session() as s:
        submitted = PurchaseOrder(po_number="PO-1", supplier_id=1, status=PurchaseOrderStatus.SUBMITTED)
        submitted.items.append(PurchaseOrderItem(product_id=1, quantity_ordered=12, quantity_received=4))
        draft = PurchaseOrder(po_number="PO-2", supplier_id=1, status=PurchaseOrderStatus.DRAFT)
        draft.items.append(PurchaseOrderItem(product_id=1, quantity_ordered=100))
        s.add_all([submitted, draft])
        s.commit()
    item = stock(client, 1)
    assert item["on_order"] == 8                       # 12 ordered - 4 received; the draft does not count
    assert item["inventory_position"] == 18


def test_list_filters_and_sorting(client):
    adjust(client, 1, -10)
    body = client.get("/api/v1/inventory", params={"status": "out_of_stock"}).json()
    assert [i["sku"] for i in body["items"]] == ["FOODS_1_001"]
    by_stock = client.get("/api/v1/inventory", params={"sort": "on_hand", "order": "desc"}).json()["items"]
    assert [i["on_hand"] for i in by_stock] == [5, 0, 0]
    assert client.get("/api/v1/inventory", params={"category": "hobbies"}).json()["total"] == 1


def test_transaction_history_newest_first_with_filters(client):
    adjust(client, 1, -1, reason="first")
    adjust(client, 1, -1, reason="second")
    adjust(client, 3, 2, reason="other product")
    history = client.get("/api/v1/inventory/transactions", params={"product_id": 1}).json()
    assert history["total"] == 2
    assert [t["reason"] for t in history["items"]] == ["second", "first"]
    assert client.get("/api/v1/inventory/transactions", params={"txn_type": "sale"}).json()["total"] == 0


def test_every_balance_change_has_a_matching_transaction(api, client):
    for qty in (-3, 5, -1):
        adjust(client, 1, qty)
    with api.app.state.make_session() as s:
        total_moved = sum(t.quantity for t in s.query(InventoryTransaction).filter_by(product_id=1))
    assert 10 + total_moved == stock(client, 1)["on_hand"] == 11
