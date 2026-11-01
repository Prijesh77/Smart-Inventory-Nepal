"""Forecast and recommendation API tests.

Extra data for these tests: 100 more days of sales for product 1 BEFORE the
shared data (2015-09-23 .. 2015-12-31), so the models have enough history
(91+ days) and the engine can measure past forecast errors. Sales follow
d % 3 (0, 1, 2, ...); the last 28 days average 27/28 = 0.964 units/day.
Background jobs run before TestClient returns, so results can be read at once.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models import CalendarDay, DailySales
from tests.conftest import login

AVG = 27 / 28
FIRST_SHARED_DAY = date(2016, 1, 1)
DEFAULT_ORIGIN = "2016-04-10"            # day after the last sales day


@pytest.fixture
def planning(api, client):
    with api.app.state.make_session() as s:
        days = [FIRST_SHARED_DAY - timedelta(days=k) for k in range(1, 101)]
        s.add_all([CalendarDay(day=d) for d in days])
        s.flush()
        # Continue the d % 3 pattern backwards so the whole series is one regular cycle.
        s.add_all([DailySales(product_id=1, sales_date=d, units=(-(k)) % 3) for k, d in enumerate(days, start=1)])
        s.commit()
    return client


def start_forecast(client, **body):
    response = client.post("/api/v1/forecasts/runs", json={"model_name": "moving_avg_28", **body})
    assert response.status_code == 202, response.text
    return client.get(f"/api/v1/forecasts/runs/{response.json()['id']}").json()


# ---------- forecasts ----------

def test_moving_average_forecast_run(planning):
    run = start_forecast(planning)
    assert run["status"] == "completed" and run["origin_date"] == DEFAULT_ORIGIN
    assert run["metrics"]["products"] == 1                    # only product 1 has sales
    assert any("Prices" in a for a in run["params"]["assumptions"])

    body = planning.get("/api/v1/forecasts/products/1").json()
    assert len(body["forecast"]) == 28
    assert body["forecast"][0]["predicted_units"] == pytest.approx(AVG, abs=1e-3)
    assert body["total_forecast"] == pytest.approx(28 * AVG, abs=0.05)
    assert body["history"][-1]["date"] == "2016-04-09"       # actuals end before the forecast starts
    assert body["actual_in_window"] == []


def test_back_dated_forecast_includes_actuals_for_checking(planning):
    run = start_forecast(planning, origin_date="2016-03-01", horizon_days=7)
    body = planning.get("/api/v1/forecasts/products/1", params={"run_id": run["id"]}).json()
    assert len(body["forecast"]) == 7 and len(body["actual_in_window"]) == 7
    assert all(p["date"] < "2016-03-01" for p in body["history"])


def test_failed_run_is_recorded_not_lost(planning):
    run = start_forecast(planning, origin_date="2015-10-01")    # only 8 days of history
    assert run["status"] == "failed" and "history" in run["error_message"]


def test_forecast_input_rules(planning, api):
    assert planning.post("/api/v1/forecasts/runs", json={"origin_date": "2016-05-01"}).status_code == 400
    assert planning.post("/api/v1/forecasts/runs", json={"model_name": "magic"}).status_code == 422
    assert planning.post("/api/v1/forecasts/runs", json={"horizon_days": 30}).status_code == 422
    assert api.post("/api/v1/forecasts/runs", json={}, headers=login(api, "viewer")).status_code == 403
    assert planning.get("/api/v1/forecasts/products/1").status_code == 404     # no run yet


def test_random_forest_needs_the_shops_own_trained_model(planning):
    # Training and forecasting with a trained forest are tested in test_demo_shop.py.
    run = start_forecast(planning, model_name="random_forest_v1")
    assert run["status"] == "failed" and "not been trained" in run["error_message"]


def test_auto_uses_the_moving_average_until_the_shop_has_a_trained_forest(planning, api, empty_model_folder):
    response = planning.post("/api/v1/forecasts/runs", json={"horizon_days": 7})          # model_name defaults to auto
    assert response.status_code == 202 and response.json()["model_name"] == "moving_avg_28"
    with api.app.state.make_session() as s:
        from app.services.forecasting import choose_model
        import json
        from ml.features.build import FEATURES
        empty_model_folder.mkdir()
        (empty_model_folder / "shop_1_random_forest.joblib").write_bytes(b"trained")
        meta = empty_model_folder / "shop_1_random_forest.json"
        meta.write_text(json.dumps({"features": FEATURES[:-1] + ["snap"]}))        # trained with old features
        model, reason = choose_model(s, "auto")
        assert model == "moving_avg_28" and "needs retraining" in reason
        meta.write_text(json.dumps({"features": FEATURES}))
        assert choose_model(s, "auto")[0] == "random_forest_v1"
        assert choose_model(s, "moving_avg_28") == ("moving_avg_28", None)

        # A forest that was LESS accurate than the moving average on the held-back days is not used.
        from app.models import ModelEvaluation
        from app.models.enums import EvaluationPeriod
        for name, wape in [("random_forest_v1", "0.61"), ("moving_avg_28", "0.48")]:
            s.add(ModelEvaluation(model_name=name, model_version="v", period=EvaluationPeriod.TEST, horizon_days=28,
                                  demand_class="all", n_observations=100, wape=wape))
        s.flush()
        model, reason = choose_model(s, "auto")
        assert model == "moving_avg_28" and "more accurate" in reason and "48% vs 61%" in reason


# ---------- recommendations ----------

def start_recommendations(client, **body):
    response = client.post("/api/v1/recommendations/runs", json=body)
    assert response.status_code == 202, response.text
    return client.get(f"/api/v1/recommendations/runs/{response.json()['id']}").json()


def test_recommendations_need_a_forecast(planning):
    assert planning.post("/api/v1/recommendations/runs", json={}).status_code == 404


def test_recommendation_run_end_to_end(planning):
    start_forecast(planning)
    run = start_recommendations(planning)
    assert run["status"] == "completed", run["error_message"]
    assert run["policy_settings"]["service_level"] == 0.95
    assert run["summary"]["counts"] == {"reorder_soon": 1, "insufficient_data": 2}

    page = planning.get("/api/v1/recommendations").json()
    assert page["run"]["id"] == run["id"] and page["total"] == 3
    first = page["items"][0]                                   # sorted by risk: most urgent first
    assert first["sku"] == "FOODS_1_001" and first["risk_category"] == "reorder_soon"
    # Hand-checkable parts: position 10; lead time 3 + review 7 = 10-day protection period.
    assert float(first["inventory_position"]) == 10
    assert float(first["forecast_lead_time_demand"]) == pytest.approx(3 * AVG, abs=0.01)
    assert float(first["forecast_protection_demand"]) == pytest.approx(10 * AVG, abs=0.01)
    assert float(first["reorder_point"]) > 10 >= float(first["forecast_protection_demand"])
    assert first["suggested_qty"] > 0 and "Order" in first["explanation"]
    assert any("measured protection-period" in w for w in first["warnings"])
    others = {i["sku"]: i for i in page["items"][1:]}
    assert others["FOODS_1_002"]["risk_category"] == "insufficient_data"
    assert others["FOODS_1_002"]["suggested_qty"] == 0


def test_higher_service_level_means_more_safety_stock(planning):
    start_forecast(planning)
    low = start_recommendations(planning, service_level=0.80)["id"]
    high = start_recommendations(planning, service_level=0.99)["id"]
    ss = lambda rid: float(planning.get("/api/v1/recommendations", params={"run_id": rid}).json()["items"][0]["safety_stock"])  # noqa: E731
    assert ss(high) > ss(low) > 0


def test_short_horizon_forecast_gives_insufficient_data(planning):
    start_forecast(planning, horizon_days=7)                    # shorter than the 10-day protection period
    start_recommendations(planning)
    item = planning.get("/api/v1/recommendations", params={"search": "FOODS_1_001"}).json()["items"][0]
    assert item["risk_category"] == "insufficient_data" and "horizon" in item["explanation"]


def test_filters_and_review_workflow(planning, api):
    start_forecast(planning)
    start_recommendations(planning)
    orders = planning.get("/api/v1/recommendations", params={"only_orders": True}).json()
    assert orders["total"] == 1
    rec_id = orders["items"][0]["id"]

    assert api.patch(f"/api/v1/recommendations/{rec_id}", json={"review_status": "approved"},
                     headers=login(api, "viewer")).status_code == 403
    approved = planning.patch(f"/api/v1/recommendations/{rec_id}", json={"review_status": "approved"}).json()
    assert approved["review_status"] == "approved" and approved["reviewed_at"]
    assert planning.get("/api/v1/recommendations", params={"review_status": "approved"}).json()["total"] == 1

    no_order = planning.get("/api/v1/recommendations", params={"risk": "insufficient_data"}).json()["items"][0]
    response = planning.patch(f"/api/v1/recommendations/{no_order['id']}", json={"review_status": "approved"})
    assert response.status_code == 400                        # nothing to order
    assert planning.patch(f"/api/v1/recommendations/{rec_id}",
                          json={"review_status": "ordered"}).status_code == 422
