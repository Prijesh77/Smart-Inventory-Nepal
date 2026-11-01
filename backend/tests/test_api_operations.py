"""Dashboard, analytics, exports, settings, sales import and simulation endpoints.

Shared data (conftest.py): sales for product 1 only, units = d % 3 over 2016-01-01..2016-04-09
(no prices); stock 10 / 0 / 5; unit cost 0.50 for all three products.
Last 28 days: 27 units. The 28 days before: 29 units (the cycle starts at 2).
"""

from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from app.models import DailySales
from ml import config
from tests.conftest import login


# ---------- dashboard and analytics ----------

def test_dashboard_summary_hand_checked(client):
    s = client.get("/api/v1/dashboard/summary").json()
    assert s["as_of"] == "2016-04-09" and s["active_products"] == 3
    assert s["units_on_hand"] == 15 and s["inventory_value"] == 7.5        # 15 x 0.50
    assert s["stock_status"] == {"ok": 1, "no_recent_demand": 2}
    assert s["sales"]["last_28_days_units"] == 27
    assert s["sales"]["change_vs_previous_28_days"] == pytest.approx((27 - 29) / 29)
    assert len(s["sales"]["daily_trend"]) == 90
    assert s["recommendations"] is None and s["forecast"] is None           # nothing run yet: no invented numbers
    assert s["purchase_orders"] == {"open": 0, "open_order_value": 0.0, "drafts": 0}
    assert s["simulated_fields"] == []          # a real shop: nothing is labelled as simulated
    # Nepali fiscal year 2072/73 (from 1 Shrawan 2072 = 17 July 2015) holds all the test sales.
    assert s["sales"]["fiscal_year"]["label"] == "2072/73" and s["sales"]["fiscal_year"]["start"] == "2015-07-17"
    assert s["sales"]["fiscal_year"]["units"] == sum(d % 3 for d in range(100))


def test_analytics(client):
    cats = {c["category"]: c for c in client.get("/api/v1/analytics/categories").json()}
    assert cats["FOODS"]["units_sold"] == 27 and cats["FOODS"]["units_on_hand"] == 10
    assert cats["FOODS"]["days_of_cover"] == pytest.approx(10 / (27 / 28), abs=0.05)
    assert cats["HOBBIES"]["units_sold"] == 0 and cats["HOBBIES"]["days_of_cover"] is None
    weekly = client.get("/api/v1/analytics/weekly-trend", params={"weeks": 4}).json()
    assert all(w["category"] == "FOODS" for w in weekly) and sum(w["units"] for w in weekly) > 0
    assert len(client.get("/api/v1/analytics/sales-trend", params={"days": 7, "product_id": 1}).json()) == 7


def test_dashboard_needs_login(api):
    assert api.get("/api/v1/dashboard/summary").status_code == 401


# ---------- exports ----------

def read_csv(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_export_products_csv(client):
    response = client.get("/api/v1/exports/products.csv")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert 'filename="products_2016-04-10.csv"' in response.headers["content-disposition"]
    rows = read_csv(response)
    assert rows[0][:2] == ["sku", "name"] and "unit_cost (simulated)" in rows[0]
    assert [r[0] for r in rows[1:]] == ["FOODS_1_001", "FOODS_1_002", "HOBBIES_1_001"]


def test_export_blocks_spreadsheet_formulas(client):
    client.post("/api/v1/products", json={"sku": "EVIL_1", "name": "=HYPERLINK(\"http://x\")",
                                          "category_code": "FOODS", "unit_price": "1.00"})
    names = {r[0]: r[1] for r in read_csv(client.get("/api/v1/exports/products.csv"))[1:]}
    assert names["EVIL_1"] == "'=HYPERLINK(\"http://x\")"


def test_other_exports(client, api):
    client.post("/api/v1/inventory/adjustments", json={"product_id": 1, "quantity": -2, "reason": "damaged"})
    txns = read_csv(client.get("/api/v1/exports/transactions.csv"))
    assert txns[1][2] == "FOODS_1_001" and txns[1][4] == "-2"          # negative number kept as a number
    assert len(read_csv(client.get("/api/v1/exports/inventory.csv"))) == 4
    assert client.get("/api/v1/exports/recommendations.csv").status_code == 404   # no run yet
    assert client.get("/api/v1/exports/secrets.csv").status_code == 422
    assert api.get("/api/v1/exports/products.csv", headers=login(api, "viewer")).status_code == 200


# ---------- settings ----------

def test_policy_settings(api):
    admin, manager = login(api, "admin"), login(api, "manager")
    defaults = api.get("/api/v1/settings/policy", headers=manager).json()
    assert defaults["service_level"] == 0.95 and defaults["forecast_horizons"] == [7, 14, 28]
    new = {**defaults, "service_level": 0.98, "ordering_cost": 4}
    assert api.put("/api/v1/settings/policy", json=new, headers=manager).status_code == 403
    assert api.put("/api/v1/settings/policy", json=new, headers=admin).status_code == 200
    assert api.get("/api/v1/settings/policy", headers=manager).json()["service_level"] == 0.98
    bad = {**defaults, "min_cycle_days": 30, "max_cycle_days": 7}
    assert api.put("/api/v1/settings/policy", json=bad, headers=admin).status_code == 422


# ---------- sales import ----------

def upload(client, path, text, **form):
    return client.post(path, files={"file": ("sales.csv", text.encode("utf-8"), "text/csv")}, data=form)


GOOD = "sku,date,units,unit_price\nFOODS_1_001,2016-04-09,7,2.50\nfoods_1_002,2016-04-10,3,\n"


def test_preview_valid_file(client):
    body = upload(client, "/api/v1/imports/sales/preview", GOOD).json()
    assert body["rows_total"] == 2 and body["rows_valid"] == 2 and body["can_import"] is True
    assert body["would_replace"] == 1 and body["would_add"] == 1    # 2016-04-09 already exists for product 1
    assert body["preview"][1]["sku"] == "FOODS_1_002"               # SKU upper-cased


def test_preview_reports_every_bad_row(client):
    bad = ("sku,date,units\nFOODS_1_001,09/04/2016,1\nNOPE,2016-04-01,1\nFOODS_1_001,2016-04-02,-3\n"
           "FOODS_1_001,2016-04-03,2\nFOODS_1_001,2016-04-03,2\n")
    body = upload(client, "/api/v1/imports/sales/preview", bad).json()
    assert body["can_import"] is False and body["rows_invalid"] == 4
    assert [(e["row"], e["column"]) for e in body["errors"]] == [(2, "date"), (3, "sku"), (4, "units"), (6, "date")]


def test_row_with_two_errors_counts_as_one_invalid_row(client):
    bad = "sku,date,units\nNOPE,23/05/2016,1\nFOODS_1_001,2016-04-12,2\n"     # row 2: bad SKU and bad date
    body = upload(client, "/api/v1/imports/sales/preview", bad).json()
    assert len(body["errors"]) == 2
    assert body["rows_total"] == 2 and body["rows_valid"] == 1 and body["rows_invalid"] == 1
    response = upload(client, "/api/v1/imports/sales", bad)            # the failed job must still be logged
    assert response.status_code == 422
    assert client.get("/api/v1/imports/jobs").json()[0]["rows_invalid"] == 1


def test_invalid_file_imports_nothing_but_is_logged(api, client):
    response = upload(client, "/api/v1/imports/sales", "sku,date,units\nFOODS_1_001,2016-04-11,5\nNOPE,2016-04-11,1\n")
    assert response.status_code == 422 and "nothing was imported" in response.json()["detail"]
    with api.app.state.make_session() as s:
        assert s.query(DailySales).filter_by(sales_date=date(2016, 4, 11)).count() == 0
    jobs = client.get("/api/v1/imports/jobs").json()
    assert jobs[0]["status"] == "failed" and jobs[0]["rows_invalid"] == 1


def test_valid_import_adds_and_replaces(client):
    response = upload(client, "/api/v1/imports/sales", GOOD)
    assert response.status_code == 201
    assert response.json()["errors"] == {"errors": [], "added": 1, "replaced": 1, "calendar_days_added": 1}
    history = client.get("/api/v1/products/1/sales", params={"start": "2016-04-09", "end": "2016-04-09"}).json()
    assert history["points"][0]["units"] == 7 and history["points"][0]["unit_price"] == "2.50"


def test_custom_column_mapping(client):
    text = "Item,Day,Qty\nFOODS_1_001,2016-04-12,4\n"
    body = upload(client, "/api/v1/imports/sales/preview", text, sku_column="Item", date_column="Day",
                  units_column="Qty", price_column="").json()
    assert body["rows_valid"] == 1


@pytest.mark.parametrize("content, message", [
    ("", "empty"),
    ("sku,date\nA,2016-01-01\n", "Missing column"),
    ("sku,date,units\n", "no data rows"),
])
def test_bad_files_rejected(client, content, message):
    response = upload(client, "/api/v1/imports/sales/preview", content)
    assert response.status_code == 400 and message in response.json()["detail"]


def test_non_utf8_rejected(client):
    response = client.post("/api/v1/imports/sales/preview",
                           files={"file": ("x.csv", "sku,date,units\nCAFÉ,2016-01-01,1\n".encode("cp1252"), "text/csv")})
    assert response.status_code == 400 and "UTF-8" in response.json()["detail"]


def test_import_needs_manager(api):
    response = api.post("/api/v1/imports/sales/preview", headers=login(api, "viewer"),
                        files={"file": ("s.csv", GOOD.encode(), "text/csv")})
    assert response.status_code == 403


# ---------- simulations ----------

def test_simulation_input_rules(api, client):
    assert client.post("/api/v1/simulations", json={"service_levels": [0.42]}).status_code == 422
    assert client.post("/api/v1/simulations", json={"ordering_cost": -1}).status_code == 422
    assert api.post("/api/v1/simulations", json={}, headers=login(api, "viewer")).status_code == 403


RESEARCH_FILES = [config.PROCESSED_DIR / "sample_daily.parquet", config.MODELS_DIR / "random_forest_v1.joblib",
                  config.MODELS_DIR / "random_forest_v1_final.joblib"]


@pytest.mark.skipif(not all(p.exists() for p in RESEARCH_FILES), reason="research data/models not present")
def test_simulation_run_produces_labelled_results(client):
    response = client.post("/api/v1/simulations", json={"name": "test", "service_levels": [0.95]})
    assert response.status_code == 202
    run = client.get(f"/api/v1/simulations/{response.json()['id']}").json()
    assert run["status"] == "completed", run["error_message"]
    assert run["results"]["note"].startswith("SIMULATED") and run["results"]["items"] == 267
    policies = {r["policy"] for r in run["results"]["summary"] if r["demand_class"] == "all"}
    assert policies == {"baseline_demand_sd", "engine_ma28", "engine_rf"}
    assert run["results"]["matched_comparisons"] == []          # needs at least 2 service levels
