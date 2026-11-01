# Phase 4, Step 1: Inventory Decision Engine

Code: [ml/inventory/formulas.py](../ml/inventory/formulas.py) (one function per formula) and [ml/inventory/recommend.py](../ml/inventory/recommend.py) (combines them into an explained recommendation).
Tests: [tests/test_inventory_engine.py](../tests/test_inventory_engine.py), 27 tests with values that can be checked on a calculator.

The engine does not depend on the database, the web app or a particular forecasting model. It takes numbers in and gives a recommendation out, which makes it easy to test, and the simulation and the API will both call the same code.

## 1. The policy in plain language: periodic review (R, s, S)

- Every **R** days (default 7) we check each item.
- If the **inventory position** is at or below the **reorder point s**, we order enough to bring it back up to the **order-up-to level S**.
- An order arrives **L** days later (the supplier lead time).

Once we decide not to order, the next chance comes R days later, and that order then takes L days to arrive. So today's stock must last **L + R days**: the *protection period*.

## 2. Formulas

| Concept | Formula | Function |
|---|---|---|
| Inventory position | on hand + on order − backorders | `inventory_position` |
| Protection period | P = L + R | `protection_period` |
| Expected demand | sum of the daily forecasts over the period | `forecast_demand` |
| Safety factor | z = Φ⁻¹(service level); 95% → 1.645 | `z_for_service_level` |
| Uncertainty over P days | σ_P = √(P·σ_e² + d²·σ_L²) | `demand_sigma_over_period` |
| Safety stock | SS = z × σ_P | `safety_stock` |
| Reorder point | s = expected demand over P + SS | `reorder_point` |
| Cycle quantity | EOQ = √(2·D·K / h), kept between 7 and 28 days of demand | `economic_order_quantity`, `cycle_quantity` |
| Order-up-to level | S = s + cycle quantity | `recommend` |
| Order quantity | S − position, raised to the minimum order quantity, rounded **up** to whole packs; 0 if position > s | `order_quantity` |
| Stockout probability | 1 − Φ((position − lead-time demand) / σ_L) | `stockout_probability` |

Where: σ_e = standard deviation of **daily forecast errors**; d = mean daily forecast; σ_L = standard deviation of the lead time in days; D = annual demand; K = cost per order; h = yearly holding cost per unit (rate × unit cost).

### Assumptions to state in the report

1. **Safety stock uses forecast errors, not raw demand variability.** The forecast already explains part of demand's ups and downs (weekdays, trends); safety stock only needs to cover what the forecast gets wrong. Using raw demand variability as well would **double-count** (Prak, Teunter & Syntetos, 2017).
2. **√P scaling assumes daily errors are independent.** In reality, a forecast that is too low tends to stay too low for several days, so √P can understate risk. The engine therefore also accepts a **measured** error over the whole period (`period_sigma_from_errors`, computed from past backtests). The simulation will use the measured version when at least 8 past periods are available.
3. **Normal approximation.** z-values and the stockout probability assume roughly normal errors. That is reasonable for faster items and weak for intermittent ones, so those items get a warning.
4. **Cycle service level**, not fill rate: 95% means about a 95% chance of no stockout per protection period. Fill rate (share of demand served) is measured in the simulation.
5. **EOQ cap.** For cheap items EOQ can mean months of stock (e.g. a $0.50 item: EOQ ≈ 121 days). The order size is kept between 7 and 28 days of demand. This is a stated business rule, configurable in `PolicySettings`.

### Trade-offs the settings control

| Setting ↑ | Effect |
|---|---|
| Service level | More safety stock → fewer stockouts, more holding cost |
| Ordering cost K | Larger, less frequent orders (EOQ grows) |
| Holding cost rate | Smaller, more frequent orders; slightly less stock |
| Review period R | Longer protection period → more safety stock, fewer order decisions |
| Lead-time variability σ_L | More safety stock |

## 3. Risk categories (checked in this order)

| Category | Rule | Meaning |
|---|---|---|
| Critical stockout risk | position < expected demand over the lead time | Even an order placed today is expected to arrive after stock runs out |
| Reorder soon | position ≤ s | Time to order |
| Excess inventory | position > S **and** more than 60 days of cover (or stock with zero forecast) | Stock is unlikely to sell soon |
| Healthy | otherwise | No action |
| Insufficient data | no forecast, or no forecast-error history | No calculation is made; manual review |

The category and order quantity are **deterministic rules**. The stockout probability is a separate **model estimate** under the normal assumption. No confidence score is invented.

## 4. Worked example (identical to `test_worked_example_matches_docs`)

**Inputs:** on hand 20, on order 10, no backorders; lead time L = 5 days; review R = 7 days; forecast 4 units/day; σ_e = 2 units/day; service level 95%; unit cost $25; ordering cost $10; holding rate 25%/year; minimum order 24; pack size 12.

| Step | Calculation | Result |
|---|---|---|
| Inventory position | 20 + 10 − 0 | **30** |
| Protection period | 5 + 7 | **12 days** |
| Lead-time demand | 5 × 4 | 20 |
| Protection demand | 12 × 4 | 48 |
| σ over 12 days | 2 × √12 | 6.93 |
| Safety stock | 1.645 × 6.93 | **11.40** |
| Reorder point s | 48 + 11.40 | **59.40** |
| EOQ | √(2 × 1,460 × 10 / (0.25 × 25)) = √4,672 | 68.35 (17 days; inside the 7–28 day range) |
| Order-up-to S | 59.40 + 68.35 | **127.75** |
| Order? | 30 ≤ 59.40 → yes | |
| Quantity | 127.75 − 30 = 97.75 → ≥ 24 → round up to packs of 12 | **108** (9 packs) |
| Order cost | 108 × $25 | **$2,700** |
| Risk category | 30 ≥ 20 (not critical); 30 ≤ 59.40 | **Reorder soon** |
| Stockout probability (model) | σ_L = 2 × √5 = 4.47; z = (30 − 20) / 4.47 = 2.24 | **1.3%** |

Generated explanation:

> Inventory position is 30 units (on hand 20 + on order 10 - backorders 0). Forecast demand over the 5-day lead time is 20.0, and over the 12-day protection period (lead time + 7-day review) 48.0. With 11.4 units of safety stock for a 95% service target, the reorder point is 59.4. Position is at or below the reorder point. Order 108 units to reach the order-up-to level of 127.7.

Note the two different risk ideas: the 1.3% chance of running out before an order placed **today** arrives is low, yet the item is still flagged "reorder soon". If we waited until the next review in 7 days, the 12-day risk would be much higher; that is what the reorder point protects against.

## 5. Research follow-up (capstone only)

The steps below were the capstone's research plan. The simulation and the M5
experiments are not part of Smart Inventory Nepal and were removed from this
repository; the product uses the engine directly on each shop's own data.

1. **Synthetic inventory parameters** (clearly labelled as simulated): unit cost from real prices, supplier lead times, minimum order quantities, pack sizes, initial stock.
2. **Simulation** of the test year, day by day: demand arrives, unmet demand is a **lost sale**, orders arrive after L days. Compare the forecast-driven policy (RF and MA-28 forecasts) with a simple baseline policy under identical conditions.
