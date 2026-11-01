# Phase 5, Step 5: Forecast and Recommendation Endpoints

Code: `backend/app/services/forecast_engine.py` (database → ml/ code), `forecasting.py`, `recommendations.py`, and routers `api/v1/forecasts.py`, `api/v1/recommendations.py`. Tests: `backend/tests/test_api_planning.py`.

## 1. Same code in research and in the app

The API does **not** re-implement anything. It rebuilds, from the database, the same item × day table the models were trained on, then calls the tested Phase 3–4 code:

| Step | Code used |
|---|---|
| Features | `ml/features/build.py` (`make_panel`, `build_rows`) |
| Forecasts | `random_forest_v1_final.joblib` (fitted on train + validation) or `ml/models/baselines.moving_average` |
| Safety stock, reorder point, order quantity, risk, explanation | `ml/inventory/recommend.py` |

Check on real data: a back-dated 28-day forecast from 2016-04-25 built from the **database** gives WAPE 69.8% (RF) vs 72.2% (MA-28), in line with the Phase 3 test-year results.

## 2. Forecast runs

- `POST /api/v1/forecasts/runs` (manager/admin) → **202 Accepted** with a `pending` run. The work runs as a **background task**, so the request returns immediately. Poll `GET /forecasts/runs/{id}` until the status is `completed` or `failed`.
- Body: `model_name` (`random_forest_v1` | `moving_avg_28`), `horizon_days` (7 | 14 | 28), optional `origin_date`.
  - Default origin = the day after the last sales data (**2016-05-23**).
  - An **earlier** origin gives a back-dated forecast. Its actual sales are returned separately, so accuracy can be checked in the app.
- Each run records the model version, origin, horizon, creation and completion time, the assumptions, the test-year WAPE and bias of that model, and any error message. A failed run is **recorded with its reason**, never silently lost.
- `GET /forecasts/products/{id}` returns three **separate** lists, so a chart cannot mix actuals and predictions:
  - `history`: actual sales before the origin;
  - `forecast`: predicted units;
  - `actual_in_window`: actual sales inside the forecast window (back-dated runs only).
- `GET /forecasts/evaluations` returns the Phase 3 backtest scores (MAE, RMSE, WAPE, bias by model, period, horizon and demand class) for the model-comparison page.

**Assumptions for days after the data (stored on every run):** prices stay at the last known price; calendar facts beyond the stored calendar are derived from the date (no SNAP or events); forecasts are of recorded sales, which can understate demand during stockouts. The 28 future calendar days published with M5 (events, SNAP) were added with `seed.py --extend-calendar`.

## 3. Recommendation runs

- `POST /api/v1/recommendations/runs` (manager/admin) → 202, background task. Optional body: `forecast_run_id` (default: latest completed), and overrides for `service_level`, `review_period_days`, `ordering_cost`, `holding_cost_rate`. Defaults come from `app_settings.policy_defaults`. The settings actually used are stored on the run.
- For every active product: current stock (on hand, on order from submitted POs, backorders), effective lead time, simulated cost, MOQ, pack size → `recommend()`.
- **Safety stock from measured errors (the Phase 4 finding).** The same model is backtested at up to 16 weekly origins whose whole protection period ended before the forecast origin:
  1. ≥ 8 complete periods → RMSE of that item's protection-period errors;
  2. otherwise ≥ 14 daily errors → daily RMSE × √days;
  3. otherwise → **insufficient data**. No number is invented.

  The method used is listed in each recommendation's `warnings`.
- Also "insufficient data": no sales history, no lead time, or a forecast horizon shorter than the protection period.
- `GET /api/v1/recommendations`: one run's results (default: latest), filtered by `risk`, `review_status`, `search`, `only_orders`; sorted by `risk` (most urgent first), `sku`, `suggested_qty`, `estimated_order_cost`, `days_of_cover`. The run summary includes counts per category and total order cost.
- `PATCH /api/v1/recommendations/{id}` (manager/admin): `approved` / `rejected` / `pending`. Only rows with a quantity > 0 can be approved. `ordered` is set automatically when a draft purchase order is created (next step). **Nothing is ever sent to a supplier.**
- `stockout_probability` is labelled as a **model estimate** (normal approximation), not an observed rate.

## 4. Dry run on the real data (rolled back, nothing saved)

RF forecast from 2016-05-23, 28 days, default policy (95% service, weekly review):

| Result | Value |
|---|---|
| Time for forecast + all recommendations | ≈ 10 s |
| Critical stockout risk | 5 |
| Reorder soon | 48 |
| Healthy | 175 |
| Excess inventory | 39 |
| Products to order | 53 (3,747 units, **$8,216 at simulated costs**) |
| Safety stock from measured protection-period errors | 267 of 267 |

Example (critical): *FOODS_2_219: position 21; forecast 24.0 over the 14-day lead time and 36.2 over the 21-day protection period; safety stock 19.0 → reorder point 55.1; position below expected lead-time demand → order 83 units now and consider expediting.* The simple stock alert (step 4) also flagged this item.

## 5. Tests

10 planning tests: MA-28 run (values = 27/28 per day, hand-checked); back-dated run returns actuals separately; failed run recorded with reason; input rules (future origin 400, unknown model 422, viewer 403, no run 404); RF run (skipped if the model file is absent); recommendations need a forecast; end-to-end run with hand-checkable lead-time and protection demand, measured-error method, insufficient data for products without history; higher service level → more safety stock; short horizon → insufficient data; filters and the review workflow. **Full suite: 167 passed.**

## 6. Try it (`/docs`, logged in as admin)

1. `POST /api/v1/forecasts/runs` with `{}` → note the `id`.
2. `GET /api/v1/forecasts/runs/{id}` until `completed` (a few seconds).
3. `POST /api/v1/recommendations/runs` with `{}`, then poll `GET /api/v1/recommendations/runs/{id}`.
4. `GET /api/v1/recommendations?only_orders=true` → the products to order, most urgent first.
