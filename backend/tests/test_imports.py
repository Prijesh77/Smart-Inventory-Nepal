"""Onboarding a new shop from Excel/CSV: suppliers, products, opening stock, sales; plus templates and
adding categories and suppliers in the app. (Sales-import details are in test_api_operations.py.)"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook, load_workbook

from app.core.security import hash_password
from app.db.tenancy import use_shop
from app.models import Shop, User
from app.models.enums import UserRole
from tests.conftest import TEST_PASSWORD, login

EMAIL = "owner@new-shop.test"


def xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def send(api, headers, import_type, content: bytes, name="data.xlsx", check=False):
    path = f"/api/v1/imports/{import_type}" + ("/preview" if check else "")
    return api.post(path, headers=headers, files={"file": (name, content, "application/octet-stream")})


@pytest.fixture
def new_shop(api):
    """A brand-new, empty shop with one manager (as made by create_shop.py)."""
    with api.app.state.plain_session() as s:
        shop = Shop(name="Shrestha Kirana Pasal")
        s.add(shop)
        s.flush()
        use_shop(s, shop.id)
        s.add(User(email=EMAIL, full_name="Owner", role=UserRole.MANAGER,
                   hashed_password=hash_password(TEST_PASSWORD, iterations=1_000)))
        s.commit()
    response = api.post("/api/v1/auth/login", data={"username": EMAIL, "password": TEST_PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


SUPPLIERS = [["Code", "Name", "Lead_Time_Days", "lead_time_sd_days", "contact_email"],     # header case is ignored
             ["ktm-grain", "Kathmandu Grain Traders", 3, 1, "orders@ktm.test"],
             ["HIM-FMCG", "Himalayan FMCG", 2.0, None, None]]
PRODUCTS = [["sku", "name", "category", "supplier_code", "unit_price", "unit_cost", "pack_size", "min_order_qty"],
            ["RICE-JEERA-5KG", "Jeera rice 5 kg", "Rice, dal & flour", "KTM-GRAIN", 780, 705, 4, 4],
            ["NOODLES-70G", "Instant noodles 70 g", "Snacks", "HIM-FMCG", 25, 21.5, 30, 30],
            ["SALT-1KG", "Salt 1 kg", "rice, dal & flour", None, "30", None, None, None]]   # same category, any case


def test_new_shop_onboards_from_excel_and_can_forecast(api, new_shop):
    h = new_shop
    assert api.get("/api/v1/products", headers=h).json()["total"] == 0

    job = send(api, h, "suppliers", xlsx(SUPPLIERS))
    assert job.status_code == 201, job.text
    assert job.json()["errors"] == {"errors": [], "added": 2, "replaced": 0}
    suppliers = {s["code"]: s for s in api.get("/api/v1/suppliers", headers=h).json()}
    assert suppliers["KTM-GRAIN"]["lead_time_days"] == 3 and suppliers["HIM-FMCG"]["contact_email"] is None

    job = send(api, h, "products", xlsx(PRODUCTS))
    assert job.status_code == 201, job.text
    assert job.json()["errors"]["added"] == 3 and job.json()["errors"]["categories_added"] == 2
    categories = api.get("/api/v1/categories", headers=h).json()
    assert sorted(c["code"] for c in categories) == ["RICE_DAL_FLOUR", "SNACKS"]
    products = {p["sku"]: p for p in api.get("/api/v1/products", headers=h).json()["items"]}
    rice = products["RICE-JEERA-5KG"]
    assert rice["unit_price"] == "780.00" and rice["pack_size"] == 4 and rice["on_hand"] == 0
    assert products["SALT-1KG"]["supplier"] is None and products["SALT-1KG"]["unit_cost"] is None

    stock = [["sku", "quantity"], ["rice-jeera-5kg", 12], ["NOODLES-70G", 150], ["SALT-1KG", 0]]
    job = send(api, h, "opening_stock", xlsx(stock))
    assert job.status_code == 201, job.text
    assert job.json()["errors"]["units"] == 162
    inventory = {r["sku"]: r["on_hand"] for r in api.get("/api/v1/inventory", headers=h).json()["items"]}
    assert inventory == {"RICE-JEERA-5KG": 12, "NOODLES-70G": 150, "SALT-1KG": 0}
    movements = api.get("/api/v1/inventory/transactions", headers=h).json()["items"]
    assert {m["txn_type"] for m in movements} == {"initial"} and len(movements) == 2     # no row for 0 units
    assert all("Opening stock" in m["reason"] for m in movements)

    # Opening stock is a one-time thing: the second time it is refused, nothing changes.
    again = send(api, h, "opening_stock", xlsx([["sku", "quantity"], ["NOODLES-70G", 1]]))
    assert again.status_code == 422
    assert again.json()["errors"]["errors"][0]["message"].endswith("change its stock with an adjustment instead")
    preview = send(api, h, "opening_stock", xlsx([["sku", "quantity"], ["NOODLES-70G", 1]]), check=True).json()
    assert "already has stock movements" in preview["errors"][0]["message"]

    # 60 days of sales, with real Excel date cells.
    start = date(2026, 9, 1)
    sales = [["sku", "date", "units", "unit_price"]]
    sales += [["NOODLES-70G", datetime.combine(start + timedelta(days=d), datetime.min.time()), 20 + d % 7, 25]
              for d in range(60)]
    job = send(api, h, "sales", xlsx(sales))
    assert job.status_code == 201, job.text
    assert job.json()["errors"]["added"] == 60
    after = {r["sku"]: r["on_hand"] for r in api.get("/api/v1/inventory", headers=h).json()["items"]}
    assert after == inventory                                       # sales history never changes stock

    # 60 days of sales is enough for the moving average and for measured forecast errors.
    rec = plan(api, h)
    assert rec["forecast"]["model_name"] == "moving_avg_28" and "not trained yet" in rec["forecast"]["params"]["model_choice"]
    noodles = rec["by_sku"]["NOODLES-70G"]
    assert noodles["risk_category"] != "insufficient_data" and noodles["safety_stock"] is not None
    assert any("measured" in w or "daily forecast errors" in w for w in noodles["warnings"])


def plan(api, h) -> dict:
    """Forecast 28 days with 'auto', then recommendations; returns both, recommendations by SKU."""
    forecast = api.post("/api/v1/forecasts/runs", headers=h, json={"horizon_days": 28})
    assert forecast.status_code == 202, forecast.text
    forecast = api.get(f"/api/v1/forecasts/runs/{forecast.json()['id']}", headers=h).json()
    assert forecast["status"] == "completed", forecast["error_message"]
    recs = api.post("/api/v1/recommendations/runs", headers=h, json={"forecast_run_id": forecast["id"]})
    assert recs.status_code == 202, recs.text
    items = api.get("/api/v1/recommendations", headers=h, params={"page_size": 100}).json()["items"]
    return {"forecast": forecast, "by_sku": {r["sku"]: r for r in items}}


def onboard(api, h, sales_days: int) -> None:
    send(api, h, "suppliers", xlsx(SUPPLIERS))
    send(api, h, "products", xlsx(PRODUCTS))
    send(api, h, "opening_stock", xlsx([["sku", "quantity"], ["NOODLES-70G", 10], ["RICE-JEERA-5KG", 40]]))
    start = date(2026, 10, 31) - timedelta(days=sales_days - 1)
    rows = [["sku", "date", "units"]]
    for d in range(sales_days):
        rows += [["NOODLES-70G", (start + timedelta(days=d)).isoformat(), 20 + d % 7],
                 ["RICE-JEERA-5KG", (start + timedelta(days=d)).isoformat(), d % 3]]
    assert send(api, h, "sales", xlsx(rows)).status_code == 201


def test_a_shop_with_three_weeks_of_sales_gets_labelled_estimates(api, new_shop):
    onboard(api, new_shop, sales_days=20)
    rec = plan(api, new_shop)
    noodles = rec["by_sku"]["NOODLES-70G"]
    # 10 in stock, about 23 sold a day: the app must say "reorder now", not "insufficient data".
    assert noodles["risk_category"] == "critical_stockout_risk" and noodles["suggested_qty"] > 0
    assert noodles["suggested_qty"] % 30 == 0                                     # rounded to the pack of 30
    assert any("ESTIMATE" in w and "20 days" in w for w in noodles["warnings"])
    assert rec["by_sku"]["SALT-1KG"]["risk_category"] == "insufficient_data"       # no sales at all: still honest


def test_less_than_two_weeks_of_sales_is_explained(api, new_shop):
    onboard(api, new_shop, sales_days=10)
    response = api.post("/api/v1/forecasts/runs", headers=new_shop, json={"horizon_days": 28})
    run = api.get(f"/api/v1/forecasts/runs/{response.json()['id']}", headers=new_shop).json()
    assert run["status"] == "failed" and "at least 14 days" in run["error_message"] and "there are 10" in run["error_message"]


def test_reimport_updates_existing_rows(api, new_shop):
    h = new_shop
    send(api, h, "suppliers", xlsx(SUPPLIERS))
    send(api, h, "products", xlsx(PRODUCTS))
    changed = [PRODUCTS[0], ["NOODLES-70G", "Noodles 70 g (new name)", "Snacks", "HIM-FMCG", 27, 23, 30, 30]]
    preview = send(api, h, "products", xlsx(changed), check=True).json()
    assert preview["would_replace"] == 1 and preview["would_add"] == 0
    assert send(api, h, "products", xlsx(changed)).status_code == 201
    noodles = api.get("/api/v1/products", headers=h, params={"search": "NOODLES"}).json()["items"][0]
    assert noodles["name"] == "Noodles 70 g (new name)" and noodles["unit_price"] == "27.00"
    supplier = [SUPPLIERS[0], ["KTM-GRAIN", "Kathmandu Grain Traders", 5, 1, None]]
    assert send(api, h, "suppliers", xlsx(supplier)).json()["errors"]["replaced"] == 1


def test_bad_rows_are_listed_and_nothing_is_imported(api, new_shop):
    h = new_shop
    send(api, h, "suppliers", xlsx(SUPPLIERS))
    bad = [PRODUCTS[0],
           ["RICE 5KG", "Rice", "Rice", "KTM-GRAIN", 780, None, None, None],     # 2: space in SKU
           ["OK-1", "Fine", "Snacks", "NOPE", 10, None, None, None],            # 3: unknown supplier
           ["OK-2", "", "Snacks", None, -5, None, 0, None],                     # 4: no name, price < 0, pack 0
           ["OK-3", "Fine", "Snacks", None, 10.555, None, None, None],          # 5: 3 decimals
           ["OK-4", "Fine", "Snacks", None, 10, None, None, None],
           ["ok-4", "Again", "Snacks", None, 10, None, None, None]]             # 7: duplicate SKU (any case)
    preview = send(api, h, "products", xlsx(bad), check=True).json()
    assert preview["can_import"] is False and preview["rows_total"] == 6 and preview["rows_invalid"] == 5
    assert [(e["row"], e["column"]) for e in preview["errors"]] == [
        (2, "sku"), (3, "supplier_code"), (4, "name"), (4, "unit_price"), (4, "pack_size"), (5, "unit_price"),
        (7, "sku")]
    assert send(api, h, "products", xlsx(bad)).status_code == 422
    assert api.get("/api/v1/products", headers=h).json()["total"] == 0               # not even the valid rows
    assert api.get("/api/v1/categories", headers=h).json() == []


@pytest.mark.parametrize("content, name, message", [
    (xlsx([["code", "name"], ["A", "B"]]), "s.xlsx", "Missing column(s): 'lead_time_days'"),
    (b"PK\x03\x04 not really a zip file", "s.xlsx", "could not be opened"),
    (xlsx([["code", "name", "lead_time_days"]]), "s.xlsx", "no data rows"),
])
def test_bad_files_are_explained(api, new_shop, content, name, message):
    response = send(api, new_shop, "suppliers", content, name=name, check=True)
    assert response.status_code == 400 and message in response.json()["detail"]


def test_csv_works_the_same_as_excel(api, new_shop):
    csv = "code,name,lead_time_days\nTERAI-OIL,Terai Oil,5\n".encode()
    assert send(api, new_shop, "suppliers", csv, name="suppliers.csv").status_code == 201


def test_unknown_import_type_and_viewer_are_refused(api, new_shop):
    assert send(api, new_shop, "secrets", xlsx(SUPPLIERS)).status_code == 422
    viewer = login(api, "viewer")
    assert send(api, viewer, "suppliers", xlsx(SUPPLIERS), check=True).status_code == 403


@pytest.mark.parametrize("import_type", ["suppliers", "products", "opening_stock", "sales"])
def test_templates_are_excel_files_that_import_cleanly(api, new_shop, import_type):
    response = api.get(f"/api/v1/imports/templates/{import_type}.xlsx", headers=new_shop)
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    book = load_workbook(io.BytesIO(response.content))
    assert book.sheetnames[1] == "Instructions"
    types = {t["type"]: t for t in api.get("/api/v1/imports/types", headers=new_shop).json()}
    header = [c.value for c in book.worksheets[0][1]]
    assert header == [c["name"] for c in types[import_type]["columns"]]

    # The examples are valid data: importing the templates in order works.
    for earlier in ["suppliers", "products", "opening_stock", "sales"]:
        content = api.get(f"/api/v1/imports/templates/{earlier}.xlsx", headers=new_shop).content
        assert send(api, new_shop, earlier, content).status_code == 201, earlier
        if earlier == import_type:
            break


def test_categories_and_suppliers_can_be_added_in_the_app(api, new_shop, client):
    h = new_shop
    created = api.post("/api/v1/categories", headers=h, json={"name": "Cold drinks"})
    assert created.status_code == 201 and created.json()["code"] == "COLD_DRINKS"
    assert api.post("/api/v1/categories", headers=h, json={"name": "Cold Drinks!"}).status_code == 409

    supplier = api.post("/api/v1/suppliers", headers=h, json={
        "code": "bag-dairy", "name": "Bagmati Dairy", "lead_time_days": 1})
    assert supplier.status_code == 201 and supplier.json()["code"] == "BAG-DAIRY"
    sid = supplier.json()["id"]
    assert api.post("/api/v1/suppliers", headers=h, json={
        "code": "BAG-DAIRY", "name": "Again", "lead_time_days": 1}).status_code == 409
    assert api.post("/api/v1/suppliers", headers=h, json={
        "code": "X", "name": "Bad", "lead_time_days": 0}).status_code == 422
    edited = api.patch(f"/api/v1/suppliers/{sid}", headers=h, json={"lead_time_days": 2})
    assert edited.status_code == 200 and edited.json()["lead_time_days"] == 2

    # A product can now be added by hand in the new shop.
    product = api.post("/api/v1/products", headers=h, json={
        "sku": "MILK-500ML", "name": "Milk 500 ml", "category_code": "COLD_DRINKS", "supplier_id": sid,
        "unit_price": "55"})
    assert product.status_code == 201, product.text

    # Another shop's manager cannot see or edit them, and a viewer cannot add them.
    assert api.patch(f"/api/v1/suppliers/{sid}", json={"name": "Hacked"}).status_code == 404     # client = test shop
    assert "BAG-DAIRY" not in {s["code"] for s in client.get("/api/v1/suppliers").json()}
    viewer = login(api, "viewer")
    assert api.post("/api/v1/categories", headers=viewer, json={"name": "X"}).status_code == 403


def test_sales_dates_can_be_written_in_bikram_sambat(api, new_shop):
    h = new_shop
    send(api, h, "suppliers", xlsx(SUPPLIERS))
    assert send(api, h, "products", xlsx(PRODUCTS)).status_code == 201
    rows = [["sku", "date", "units"],
            ["NOODLES-70G", "2083-07-14", 20],                    # BS text = 31 Oct 2026
            ["NOODLES-70G", "2083/07/15", 21],                    # BS with slashes = 1 Nov 2026
            ["NOODLES-70G", datetime(2083, 7, 13), 19],           # an Excel date cell typed as a BS date
            ["NOODLES-70G", "2026-10-29", 18]]                    # AD still works
    job = send(api, h, "sales", xlsx(rows))
    assert job.status_code == 201, job.text
    pid = api.get("/api/v1/products", headers=h, params={"search": "NOODLES"}).json()["items"][0]["id"]
    history = api.get(f"/api/v1/products/{pid}/sales", headers=h,
                      params={"start": "2026-10-29", "end": "2026-11-01"}).json()
    assert {p["sales_date"]: p["units"] for p in history["points"]} == {
        "2026-10-29": 18, "2026-10-30": 19, "2026-10-31": 20, "2026-11-01": 21}

    bad = send(api, h, "sales", xlsx([["sku", "date", "units"], ["NOODLES-70G", "2083-07-31", 1]]), check=True).json()
    assert "not a real BS date" in bad["errors"][0]["message"]           # Kartik 2083 has only 30 days
