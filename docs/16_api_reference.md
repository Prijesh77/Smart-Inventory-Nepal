# Phase 5 Complete: API Reference

Interactive documentation: **http://127.0.0.1:8000/docs** (generated from the code). Start the server from `backend`:

```bash
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Base path `/api/v1`. **Reads** need any login (viewer, manager or admin). **Changes** need manager or admin unless marked *admin*. Errors always look like `{"detail": "..."}`: 400 rule broken, 401 not logged in, 403 role not allowed, 404 not found, 409 conflict, 422 invalid input.

## Endpoints (41 paths)

| Area | Endpoints | Doc |
|---|---|---|
| Health and auth | `GET /health` (public) · `POST /auth/login` (public) · `GET /auth/me` | [12](12_authentication.md) |
| Users (*admin*) | `GET/POST /users` · `PATCH /users/{id}` | [12](12_authentication.md) |
| Dashboard | `GET /dashboard/summary` | below |
| Analytics | `GET /analytics/sales-trend` · `/weekly-trend` · `/categories` | below |
| Products | `GET/POST /products` · `GET/PATCH /products/{id}` · `GET /products/{id}/sales` · `GET /categories` · `GET /suppliers` | [11](11_seed_and_api.md) |
| Inventory | `GET /inventory` · `/inventory/{id}` · `/inventory/alerts` · `/inventory/transactions` · `POST /inventory/adjustments` | [13](13_inventory_api.md) |
| Forecasts | `POST/GET /forecasts/runs` · `GET /forecasts/runs/{id}` · `GET /forecasts/products/{id}` · `GET /forecasts/evaluations` | [14](14_forecast_and_recommendation_api.md) |
| Recommendations | `POST/GET /recommendations/runs` · `GET /recommendations/runs/{id}` · `GET /recommendations` · `PATCH /recommendations/{id}` | [14](14_forecast_and_recommendation_api.md) |
| Purchase orders | `GET/POST /purchase-orders` · `POST /purchase-orders/from-recommendations` · `GET/PATCH /purchase-orders/{id}` · `POST …/{id}/submit` · `/receive` · `/cancel` | [15](15_purchase_orders_api.md) |
| Import | `POST /imports/sales/preview` · `POST /imports/sales` · `GET /imports/jobs` | below |
| Export | `GET /exports/{products, inventory, transactions, recommendations, purchase-orders, forecast}.csv` | below |
| Simulations | `POST/GET /simulations` · `GET /simulations/{id}` | below |
| Settings | `GET /settings/policy` · `PUT /settings/policy` (*admin*) · `GET /settings/currency` · `PUT /settings/currency` (*admin*) | below |

## Dashboard and analytics

`GET /dashboard/summary` is computed live; nothing is hard-coded. It returns:

- **Stock:** data date (`as_of`), active products, units on hand, inventory value at cost, and stock-status counts.
- **Sales:** last 28 days (units, revenue, change vs the previous 28 days) and a 90-day daily trend.
- **Planning:** the latest recommendation run (products to reorder, critical, excess, estimated order cost) and the latest forecast run (predicted units for the next 7/14/28 days). Both are **`null` when nothing has been run yet**, never an invented number.
- **Activity:** open and draft purchase orders, and the 10 most recent stock movements.
- `simulated_fields`: which values depend on simulated inputs, so the UI can label them.

Analytics: daily units and revenue (store, category or product), weekly units per category, and per category the units sold, revenue, stock, value and days of cover.

Real data: 267 products, 15,368 units ($30,235 simulated value), 14,103 units sold in the last 28 days ($44,687). Computed in about 0.13 s.

## Sales CSV import

1. `POST /imports/sales/preview` (multipart: `file`, plus optional `sku_column`, `date_column`, `units_column`, `price_column`). Returns totals, valid/invalid counts, how many rows would be **added** vs **replaced**, row-numbered errors (up to 200), and the first 20 valid rows.
2. `POST /imports/sales`: imports **all rows or none**. If any row is invalid → **422** and nothing is written, but the job is still recorded as `failed` with its errors.

| Check | Example error |
|---|---|
| Required columns present | "Missing column(s): units -> 'units'. File columns: …" |
| Known SKU (case-insensitive) | "Unknown SKU 'NOPE' (create the product first)" |
| Date `YYYY-MM-DD` | "Date '09/04/2016' is not YYYY-MM-DD" |
| Units a whole number ≥ 0 | "Units '-3' must be a whole number >= 0" |
| Price ≥ 0, ≤ 2 decimals (optional) | "Price … must be >= 0 with at most 2 decimals" |
| No duplicate SKU + date in the file | "Duplicate row for … on …" |
| UTF-8, ≤ 5 MB, ≤ 200,000 rows, not empty | "File is not UTF-8 text; save it as 'CSV UTF-8'" |

Imported sales are **demand history**: they feed forecasts but do not change stock (stock changes only through adjustments and receipts). Missing calendar days are added automatically.

## CSV export

Six datasets. Every file:

- downloads as `<dataset>_<date>.csv`, UTF-8 with a byte-order mark so Excel opens it correctly;
- marks columns based on simulated inputs with **"(simulated)"**, and the stockout probability with "(model estimate)";
- is **protected against CSV injection**: text cells starting with `= + - @` get an apostrophe, so a spreadsheet will not run them as formulas. Numbers, including negatives, are left as numbers.

## Simulations

`POST /simulations` (manager/admin) runs the Phase 4 experiment as a background job (about 10–30 s) on the research data set. Options: `service_levels` (any of 0.6–0.99), `ordering_cost`, `holding_cost_rate`, `uncertain_lead_time`. Results: fill rate, stockouts, lost units, stock value, holding/ordering/total cost per policy, service level and demand class, plus cost-at-the-same-fill-rate comparisons when two or more service levels are chosen. Every result carries a **"SIMULATED"** note.

## Settings

`GET /settings/policy` returns the defaults used by new recommendation runs: service level, review period, ordering cost, holding rate, order-size limits, excess threshold and forecast horizons. `PUT` (*admin*) validates them, e.g. max cycle ≥ min cycle.

`GET /settings/currency` returns the rupee exchange rate used for display: `npr_per_usd`, `rate_date`, `rate_source`. The default is the Nepal Rastra Bank selling rate published for 29 Oct 2026: Rs 152.66 = $1. `PUT` (*admin*) replaces it; the rate must be above 0. Every amount in the API stays in **US dollars**, the M5 data's currency. The frontend converts to rupees only for display, and converts typed rupee amounts back to dollars (to the cent) before sending them.

## Changes in this step

- `ml/config.py` (and `ml/inventory/synthetic.py`) now use **absolute** project paths, so the research code works when called from the API's folder. Behaviour is unchanged.

## Tests

`backend/tests/test_api_operations.py`, 19 tests: hand-checked dashboard figures; analytics; CSV content, file name and formula protection; settings permissions and validation; import preview, row-numbered errors, rejection of a whole bad file (nothing written, job logged), add + replace, custom column mapping, bad files, non-UTF-8, permissions; simulation input rules and a full simulation run. **Full suite: 203 passed.**
