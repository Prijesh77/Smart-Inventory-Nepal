"""Purchase-order tests. Shared data (conftest.py): supplier 1 (SUP_A, lead time 3 days)
supplies products 1-3; product 1 has 10 on hand and unit cost 0.50. App 'today' = 2016-04-10."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import RecommendationRun, ReorderRecommendation, Supplier
from app.models.enums import ReviewStatus, RiskCategory, RunStatus
from tests.conftest import login


def add_recommendations(api, specs):
    """specs: list of (product_id, qty, review_status). Returns recommendation ids."""
    with api.app.state.make_session() as s:
        run = RecommendationRun(policy_settings={}, status=RunStatus.COMPLETED)
        s.add(run)
        s.flush()
        recs = [ReorderRecommendation(recommendation_run_id=run.id, product_id=pid, on_hand=Decimal(0),
                                      inventory_position=Decimal(0), lead_time_days=3, suggested_qty=qty,
                                      risk_category=RiskCategory.REORDER_SOON, explanation="test",
                                      review_status=status) for pid, qty, status in specs]
        s.add_all(recs)
        s.commit()
        return [r.id for r in recs]


def draft(client, lines=None, supplier_id=1):
    response = client.post("/api/v1/purchase-orders", json={
        "supplier_id": supplier_id, "lines": lines or [{"product_id": 1, "quantity": 12}]})
    assert response.status_code == 201, response.text
    return response.json()


def stock(client, product_id=1):
    return client.get(f"/api/v1/inventory/{product_id}").json()


# ---------- create ----------

def test_manual_draft_uses_product_cost_and_numbers_orders(client):
    po = draft(client, [{"product_id": 1, "quantity": 12}, {"product_id": 3, "quantity": 2, "unit_cost": "1.25"}])
    assert po["po_number"] == f"PO-{po['id']:06d}" and po["status"] == "draft"
    assert [(line["sku"], line["line_total"]) for line in po["lines"]] == [("FOODS_1_001", "6.00"), ("HOBBIES_1_001", "2.50")]
    assert po["total_units"] == 14 and po["total_cost"] == "8.50"
    assert "nothing is sent to suppliers" in po["note"]


@pytest.mark.parametrize("lines, expected", [
    ([{"product_id": 1, "quantity": 0}], 422),
    ([], 422),
    ([{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 2}], 400),   # duplicate product
    ([{"product_id": 999, "quantity": 1}], 422),
])
def test_invalid_lines(client, lines, expected):
    assert client.post("/api/v1/purchase-orders", json={"supplier_id": 1, "lines": lines}).status_code == expected


def test_product_must_belong_to_supplier(api, client):
    with api.app.state.make_session() as s:
        s.add(Supplier(code="SUP_B", name="Supplier B", lead_time_days=5))
        s.commit()
    response = client.post("/api/v1/purchase-orders", json={"supplier_id": 2, "lines": [{"product_id": 1, "quantity": 1}]})
    assert response.status_code == 422 and "not supplied by" in response.json()["detail"]


def test_drafts_from_approved_recommendations(api, client):
    approved, rejected = add_recommendations(api, [(1, 24, ReviewStatus.APPROVED), (3, 6, ReviewStatus.REJECTED)])
    response = client.post("/api/v1/purchase-orders/from-recommendations", json={})
    assert response.status_code == 201
    [po] = response.json()                                     # one supplier -> one order
    assert [(line["product_id"], line["quantity_ordered"], line["recommendation_id"]) for line in po["lines"]] == [(1, 24, approved)]
    assert po["expected_date"] == "2016-04-13"                 # app today + 3-day lead time
    recs = client.get("/api/v1/recommendations", params={"run_id": 1}).json()["items"]
    assert {r["id"]: r["review_status"] for r in recs} == {approved: "ordered", rejected: "rejected"}
    # Already ordered: cannot be ordered twice.
    assert client.post("/api/v1/purchase-orders/from-recommendations", json={}).status_code == 404
    assert client.post("/api/v1/purchase-orders/from-recommendations",
                       json={"recommendation_ids": [approved]}).status_code == 409


# ---------- lifecycle ----------

def test_submit_counts_as_on_order(client):
    po = draft(client)
    assert stock(client)["on_order"] == 0                      # drafts do not count
    submitted = client.post(f"/api/v1/purchase-orders/{po['id']}/submit").json()
    assert submitted["status"] == "submitted" and submitted["submitted_at"]
    assert submitted["expected_date"] == "2016-04-13"
    assert stock(client)["on_order"] == 12 and stock(client)["inventory_position"] == 22
    assert client.post(f"/api/v1/purchase-orders/{po['id']}/submit").status_code == 409


def test_partial_then_full_receipt_updates_stock_with_audit(client):
    po = draft(client)
    client.post(f"/api/v1/purchase-orders/{po['id']}/submit")
    line_id = po["lines"][0]["id"]

    part = client.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={"lines": [{"item_id": line_id, "quantity": 5}]})
    assert part.status_code == 200 and part.json()["status"] == "partially_received"
    assert stock(client)["on_hand"] == 15 and stock(client)["on_order"] == 7

    over = client.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={"lines": [{"item_id": line_id, "quantity": 8}]})
    assert over.status_code == 409 and stock(client)["on_hand"] == 15        # nothing booked

    done = client.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={"lines": [{"item_id": line_id, "quantity": 7}]}).json()
    assert done["status"] == "received" and done["received_at"]
    assert stock(client)["on_hand"] == 22 and stock(client)["on_order"] == 0

    receipts = client.get("/api/v1/inventory/transactions", params={"txn_type": "receipt"}).json()["items"]
    assert [(t["quantity"], t["purchase_order_id"], t["created_by_email"]) for t in receipts] == [
        (7, po["id"], "manager@test.local"), (5, po["id"], "manager@test.local")]


def test_receiving_is_all_or_nothing(client):
    po = draft(client, [{"product_id": 1, "quantity": 4}, {"product_id": 3, "quantity": 2}])
    client.post(f"/api/v1/purchase-orders/{po['id']}/submit")
    a, b = (line["id"] for line in po["lines"])
    response = client.post(f"/api/v1/purchase-orders/{po['id']}/receive",
                           json={"lines": [{"item_id": a, "quantity": 4}, {"item_id": b, "quantity": 3}]})
    assert response.status_code == 409
    assert stock(client, 1)["on_hand"] == 10                   # first line rolled back too
    assert client.get(f"/api/v1/purchase-orders/{po['id']}").json()["status"] == "submitted"


def test_cannot_receive_a_draft(client):
    po = draft(client)
    response = client.post(f"/api/v1/purchase-orders/{po['id']}/receive",
                           json={"lines": [{"item_id": po["lines"][0]["id"], "quantity": 1}]})
    assert response.status_code == 409


def test_edit_only_while_draft(client):
    po = draft(client)
    edited = client.patch(f"/api/v1/purchase-orders/{po['id']}",
                          json={"notes": "Urgent", "lines": [{"product_id": 3, "quantity": 4}]}).json()
    assert edited["notes"] == "Urgent" and [line["product_id"] for line in edited["lines"]] == [3]
    client.post(f"/api/v1/purchase-orders/{po['id']}/submit")
    assert client.patch(f"/api/v1/purchase-orders/{po['id']}", json={"notes": "x"}).status_code == 409


def test_cancel_returns_recommendations_to_approved(api, client):
    [rec_id] = add_recommendations(api, [(1, 12, ReviewStatus.APPROVED)])
    [po] = client.post("/api/v1/purchase-orders/from-recommendations", json={}).json()
    cancelled = client.post(f"/api/v1/purchase-orders/{po['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    recs = client.get("/api/v1/recommendations", params={"run_id": 1}).json()["items"]
    assert recs[0]["id"] == rec_id and recs[0]["review_status"] == "approved"
    assert client.post(f"/api/v1/purchase-orders/{po['id']}/cancel").status_code == 409


def test_cannot_cancel_after_receiving(client):
    po = draft(client)
    client.post(f"/api/v1/purchase-orders/{po['id']}/submit")
    client.post(f"/api/v1/purchase-orders/{po['id']}/receive",
                json={"lines": [{"item_id": po["lines"][0]["id"], "quantity": 1}]})
    assert client.post(f"/api/v1/purchase-orders/{po['id']}/cancel").status_code == 409


# ---------- access and listing ----------

def test_viewer_can_read_not_write(api, client):
    po = draft(client)
    viewer = login(api, "viewer")
    assert api.get(f"/api/v1/purchase-orders/{po['id']}", headers=viewer).status_code == 200
    assert api.post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=viewer).status_code == 403
    assert api.post("/api/v1/purchase-orders", headers=viewer,
                    json={"supplier_id": 1, "lines": [{"product_id": 1, "quantity": 1}]}).status_code == 403


def test_list_filters(client):
    first, second = draft(client), draft(client)
    client.post(f"/api/v1/purchase-orders/{second['id']}/submit")
    assert client.get("/api/v1/purchase-orders").json()["total"] == 2
    drafts = client.get("/api/v1/purchase-orders", params={"status": "draft"}).json()["items"]
    assert [p["id"] for p in drafts] == [first["id"]]
    assert client.get("/api/v1/purchase-orders/999").status_code == 404
