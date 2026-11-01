"""End-to-end business workflow through the HTTP API, checking that every step
feeds the next one:

  forecast -> recommendations -> approve -> draft order -> submit (on order)
  -> receive (stock + audit) -> new recommendations see the higher stock
  -> dashboard and CSV export reflect it all.

Data: the shared test data plus 100 earlier days of sales for product 1
(the `planning` fixture), so the models and error measurement have history.
"""

from __future__ import annotations

import csv
import io

import pytest

from tests.conftest import login
from tests.test_api_planning import planning  # noqa: F401  (fixture)


def run_until_done(client, path: str, body: dict) -> dict:
    """Start a background run; TestClient finishes background tasks before returning."""
    response = client.post(path, json=body)
    assert response.status_code == 202, response.text
    run = client.get(f"{path}/{response.json()['id']}").json()
    assert run["status"] == "completed", run.get("error_message")
    return run


def product1_recommendation(client, run_id: int) -> dict:
    page = client.get("/api/v1/recommendations", params={"run_id": run_id, "search": "FOODS_1_001"}).json()
    return page["items"][0]


def test_full_reorder_workflow(planning, api):  # noqa: F811
    client = planning                                       # logged in as a manager

    # 1. Forecast and recommendations
    forecast = run_until_done(client, "/api/v1/forecasts/runs", {"model_name": "moving_avg_28", "horizon_days": 28})
    first = run_until_done(client, "/api/v1/recommendations/runs", {"forecast_run_id": forecast["id"]})
    rec = product1_recommendation(client, first["id"])
    assert rec["risk_category"] == "reorder_soon" and rec["suggested_qty"] > 0
    qty = rec["suggested_qty"]
    stock_before = client.get("/api/v1/inventory/1").json()
    assert stock_before["on_hand"] == 10 and stock_before["on_order"] == 0

    # 2. Approve, then draft purchase order (one per supplier)
    assert client.patch(f"/api/v1/recommendations/{rec['id']}", json={"review_status": "approved"}).status_code == 200
    [po] = client.post("/api/v1/purchase-orders/from-recommendations",
                       json={"recommendation_ids": [rec["id"]]}).json()
    assert po["status"] == "draft" and po["lines"][0]["quantity_ordered"] == qty
    assert product1_recommendation(client, first["id"])["review_status"] == "ordered"
    assert client.get("/api/v1/inventory/1").json()["on_order"] == 0        # drafts do not count

    # 3. Submit: now on order, stock position includes it
    assert client.post(f"/api/v1/purchase-orders/{po['id']}/submit").json()["status"] == "submitted"
    on_order = client.get("/api/v1/inventory/1").json()
    assert on_order["on_order"] == qty and on_order["inventory_position"] == 10 + qty

    # 4. Receive in two deliveries: stock goes up, each with an audit row linked to the order
    line = po["lines"][0]["id"]
    part = qty // 2
    client.post(f"/api/v1/purchase-orders/{po['id']}/receive", json={"lines": [{"item_id": line, "quantity": part}]})
    done = client.post(f"/api/v1/purchase-orders/{po['id']}/receive",
                       json={"lines": [{"item_id": line, "quantity": qty - part}]}).json()
    assert done["status"] == "received"
    stock_after = client.get("/api/v1/inventory/1").json()
    assert stock_after["on_hand"] == 10 + qty and stock_after["on_order"] == 0
    receipts = client.get("/api/v1/inventory/transactions",
                          params={"product_id": 1, "txn_type": "receipt"}).json()["items"]
    assert sorted(r["quantity"] for r in receipts) == sorted([part, qty - part])
    assert {r["purchase_order_id"] for r in receipts} == {po["id"]}
    assert receipts[0]["balance_after"] == 10 + qty

    # 5. A new recommendation run sees the higher stock and no longer asks to reorder
    second = run_until_done(client, "/api/v1/recommendations/runs", {"forecast_run_id": forecast["id"]})
    rec2 = product1_recommendation(client, second["id"])
    assert float(rec2["inventory_position"]) == 10 + qty
    assert rec2["suggested_qty"] == 0 and rec2["risk_category"] in {"healthy", "excess_inventory"}

    # 6. Dashboard and exports reflect the workflow
    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["recommendations"]["run_id"] == second["id"]
    assert summary["purchase_orders"]["open"] == 0
    assert summary["units_on_hand"] == 15 + qty
    assert summary["recent_activity"][0]["txn_type"] == "receipt"
    rows = list(csv.DictReader(io.StringIO(client.get("/api/v1/exports/purchase-orders.csv").content.decode("utf-8-sig"))))
    assert rows[0]["po_number"] == po["po_number"] and rows[0]["quantity_received"] == str(qty)

    # 7. A viewer can see all of it but change none of it
    viewer = login(api, "viewer")
    assert api.get(f"/api/v1/purchase-orders/{po['id']}", headers=viewer).status_code == 200
    assert api.post(f"/api/v1/purchase-orders/{po['id']}/cancel", headers=viewer).status_code == 403


def test_cannot_order_the_same_recommendation_twice(planning):  # noqa: F811
    client = planning
    forecast = run_until_done(client, "/api/v1/forecasts/runs", {"model_name": "moving_avg_28"})
    run = run_until_done(client, "/api/v1/recommendations/runs", {"forecast_run_id": forecast["id"]})
    rec = product1_recommendation(client, run["id"])
    client.patch(f"/api/v1/recommendations/{rec['id']}", json={"review_status": "approved"})
    assert client.post("/api/v1/purchase-orders/from-recommendations", json={"recommendation_ids": [rec["id"]]}).status_code == 201
    second = client.post("/api/v1/purchase-orders/from-recommendations", json={"recommendation_ids": [rec["id"]]})
    assert second.status_code == 409


@pytest.mark.parametrize("service_level", [0.80, 0.99])
def test_service_level_changes_the_order(planning, service_level):  # noqa: F811
    """Higher target -> at least as much safety stock and order quantity (hand-checkable direction)."""
    client = planning
    forecast = run_until_done(client, "/api/v1/forecasts/runs", {"model_name": "moving_avg_28"})
    low = run_until_done(client, "/api/v1/recommendations/runs", {"forecast_run_id": forecast["id"], "service_level": 0.5})
    chosen = run_until_done(client, "/api/v1/recommendations/runs",
                            {"forecast_run_id": forecast["id"], "service_level": service_level})
    base, rec = product1_recommendation(client, low["id"]), product1_recommendation(client, chosen["id"])
    assert float(rec["safety_stock"]) > float(base["safety_stock"])
    assert rec["suggested_qty"] >= base["suggested_qty"]
