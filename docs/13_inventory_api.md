# Phase 5, Step 4: Inventory Endpoints

Code: [backend/app/services/inventory.py](../backend/app/services/inventory.py), [backend/app/api/v1/inventory.py](../backend/app/api/v1/inventory.py). Tests: [backend/tests/test_api_inventory.py](../backend/tests/test_api_inventory.py).

## 1. The audit rule

**Stock only changes through one function, `apply_movement`.** Inside a single database transaction it:

1. **locks** the product's balance row (`SELECT … FOR UPDATE`), so two people adjusting at the same moment cannot both start from the same old number;
2. refuses the change if stock would go negative (**409**);
3. updates `inventory_balances.on_hand`;
4. inserts an `inventory_transactions` row: type, signed quantity, balance after, reason, user, time.

If any step fails, nothing is saved. A test confirms that the opening stock plus the sum of all transactions always equals the current balance. Later steps (receiving purchase orders) will reuse the same function.

| Manual movement type | Direction | Example |
|---|---|---|
| `adjustment` | + or − | Stock count correction, damage, loss |
| `sale` | − only | Sale recorded outside the sales import |
| `return` | + only | Customer return |
| `receipt`, `initial` | not allowed manually | Created by purchase-order receiving or by setup |

A reason (3–500 characters) is always required.

## 2. Stock figures

| Field | Meaning |
|---|---|
| `on_hand` | Units on the shelf |
| `on_order` | Σ(ordered − received) over **submitted / partially received** purchase orders. Drafts do not count. Calculated, never stored |
| `inventory_position` | on_hand + on_order − backorders |
| `avg_daily_sales` | Units per available day over the last 28 days of data |
| `days_of_cover` | inventory_position ÷ avg_daily_sales |
| `lead_time_days` | Product override, else the supplier's lead time |

### Stock status (a simple, transparent rule)

| Status | Rule |
|---|---|
| `no_recent_demand` | No sales in the last 28 days |
| `out_of_stock` | on_hand = 0 (with recent demand) |
| `low` | inventory_position < avg_daily_sales × lead_time_days, i.e. stock will not last until a new order could arrive |
| `ok` | Otherwise |

This is a **rule-of-thumb alert**, not a forecast. The forecast-based risk categories (critical / reorder soon / healthy / excess) come from the reorder engine in the recommendations step.

## 3. Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/v1/inventory` | Any logged-in user | Stock list: `page`, `page_size`, `search`, `category`, `status`, `sort` (sku / on_hand / days_of_cover / inventory_position / avg_daily_sales), `order` |
| GET | `/api/v1/inventory/{product_id}` | Any | One product's stock figures |
| GET | `/api/v1/inventory/alerts` | Any | Out-of-stock and low products, most urgent first |
| GET | `/api/v1/inventory/transactions` | Any | Audit log, newest first; filter by `product_id`, `txn_type`, `start`, `end` |
| POST | `/api/v1/inventory/adjustments` | Manager / admin | Record an adjustment, sale or return → 201 with the transaction; 409 if stock would go negative; 404 unknown product; 400/422 invalid |

## 4. Results on the seeded data (simulated stock, real sales)

- 267 active products: **252 ok, 4 low, 1 out of stock, 10 with no recent demand**.
- 5 alerts, for example HOUSEHOLD_2_342 (out of stock, 0.71 units/day) and FOODS_2_385 (4.5 days of cover vs a 14-day lead time).
- 266 transactions in the log (the opening balances).
- The stock-list query takes about 0.1 s for all products.

## 5. Tests

18 inventory tests: hand-checked stock figures; adjustment updates balance and writes an audit row with the user; negative stock rejected with **nothing** written; direction rules per type; receipts/initial not allowed manually; invalid input; 404; sale and return; viewer can read but not adjust (403); low → out-of-stock alerts; on-order counts only submitted POs (drafts excluded); filters and sorting; history order and filters; balance = opening + Σ transactions. **Full suite: 157 passed.**
