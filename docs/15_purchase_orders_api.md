# Phase 5, Step 6: Purchase Orders

Code: [backend/app/services/purchasing.py](../backend/app/services/purchasing.py), [backend/app/api/v1/purchase_orders.py](../backend/app/api/v1/purchase_orders.py). Tests: [backend/tests/test_api_purchase_orders.py](../backend/tests/test_api_purchase_orders.py), plus one PostgreSQL lifecycle test.

> **Orders are only recorded in this app. Nothing is ever sent to a supplier.** Every purchase-order response repeats this in its `note` field.

## 1. Status flow

```
draft ──submit──► submitted ──receive──► partially_received ──receive──► received
  │                   │
  └──────cancel───────┴──► cancelled     (only while nothing has been received)
```

| Action | Allowed from | Effect |
|---|---|---|
| Create (manual) | — | Draft. Every product must belong to the order's supplier; no duplicate lines; quantity > 0; unit cost defaults to the product's cost |
| Create from recommendations | — | **One draft per supplier** from APPROVED recommendations (default: latest run). Linked recommendations become `ordered`, so they cannot be ordered twice. Expected date = app today + supplier lead time |
| Edit | draft | Notes, expected date, or replace all lines |
| Submit | draft | Marks it as placed; it now counts in **on order** and inventory position |
| Receive | submitted, partially received | Per line, quantity ≤ outstanding. Adds stock through `apply_movement` (receipt transaction linked to the PO and the user). **All lines or none** |
| Cancel | draft, submitted (nothing received) | Linked recommendations go back to `approved` |

Each PO gets a number like `PO-000123` from its database ID, so numbers are always unique. "App today" is the day after the last sales data (2016-05-23), because the app runs on historical data.

## 2. Endpoints (reads: any logged-in user; changes: manager or admin)

| Method | Path |
|---|---|
| GET | `/api/v1/purchase-orders?status=&supplier_id=&page=&page_size=` |
| GET | `/api/v1/purchase-orders/{id}`: lines with SKU, ordered/received/outstanding, line totals, order total |
| POST | `/api/v1/purchase-orders` |
| POST | `/api/v1/purchase-orders/from-recommendations` |
| PATCH | `/api/v1/purchase-orders/{id}` |
| POST | `/api/v1/purchase-orders/{id}/submit` · `/receive` · `/cancel` |

Errors: 404 unknown order; 409 wrong status, over-receiving or ordering twice; 400 duplicate lines or empty order; 422 invalid input or a product not supplied by that supplier.

## 3. End-to-end workflow now available in the API

1. `POST /forecasts/runs` → forecast all products.
2. `POST /recommendations/runs` → explained recommendations.
3. `PATCH /recommendations/{id}` → approve.
4. `POST /purchase-orders/from-recommendations` → draft orders per supplier.
5. `POST /purchase-orders/{id}/submit` → on order increases.
6. `POST /purchase-orders/{id}/receive` → stock increases, with receipt audit records.

## 4. Tests

16 API tests: manual draft totals and numbering; invalid lines; supplier mismatch; drafts from approved recommendations (rejected ones ignored, no double ordering); submit → on order; partial then full receipt with audit rows; over-receiving refused with nothing booked; **all-or-nothing** multi-line receipt; cannot receive a draft; edit only while draft; cancel returns recommendations to approved; cannot cancel after receiving; viewer read-only; list filters.

PostgreSQL integration test: draft → submit → receive on the real database, exercising the `SELECT … FOR UPDATE` row locks, rolled back afterwards. The database was confirmed unchanged.

**Full suite: 184 passed** (183 on SQLite + the PostgreSQL tests).

## 5. Development note

On this machine `uvicorn --reload` sometimes misses file changes (the project path contains spaces). If a new endpoint does not appear on `/docs`, stop the server (Ctrl+C) and start it again.
