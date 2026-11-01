# Smart Inventory Nepal

Demand forecasting and explainable reorder recommendations for Nepali retailers and wholesalers: kirana shops, pharmacies, hardware, cosmetics and distributors.

> **Status: early development.** This repository starts from the author's capstone project, *Smart Inventory and Reorder Recommendation System Using Machine Learning* (tag `capstone-v1.0` in [the capstone repository](https://github.com/Prijesh77/Smart-Inventory-and-Reorder-Recommendation-System-Using-Machine-Learning)). The code still runs on the capstone's research setup, described under "Current state" below, and is being turned into a product.

## What it does (inherited from the capstone)

- **Forecasts each product's demand** with machine learning, falling back to moving averages for slow sellers.
- **Recommends when and how much to reorder** using a periodic-review (R, s, S) policy. It accounts for safety stock, supplier lead time, stock already on order, minimum order quantity and pack size, and explains every number in plain language.
- **Runs purchase orders:** draft, submit, then partial or full receipt, which updates stock automatically.
- **Keeps an audit log of every stock movement** and supports validated CSV import.
- **Controls access with roles:** admin, manager and viewer.
- **Shows amounts in rupees or dollars** with lakh/crore formatting.

## Current state and the plan

| Area | Now (from the capstone) | Product goal |
|---|---|---|
| Data | Demo data from the M5 Walmart competition. It cannot be used commercially and is **not** in this repository. | Each shop's own data, imported from Excel or accounting exports (e.g. Tally) |
| Forecast model | One Random Forest trained on M5 data (`models/*.joblib`, not in the repository) | Trained automatically per shop on its own sales; simple methods until there is enough history |
| Businesses | One store | Many shops, each with private, separate data and users |
| Currency | Stored in US dollars, shown as Rs or $ | Stored natively in NPR |
| Calendar | Gregorian dates; US events and SNAP days | Bikram Sambat dates, Shrawan–Ashadh fiscal year, Dashain/Tihar/Chhath and other festivals as forecast features |
| Tax | None | 13% VAT on purchases; supplier PAN/VAT numbers |
| Language | English | Nepali / English |
| Analytics simulation | Research simulation on M5 data (`ml/experiments`, `experiments/results`) | Replaced by shop-level reports |

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL.
- **Machine learning:** pandas, scikit-learn (`ml/`).
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Recharts.
- **Tests:** pytest, Vitest, Playwright.
- **Deployment:** Docker Compose (PostgreSQL, API, nginx).

## Development setup (Windows)

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
```

Copy `.env.example` to `.env` and set your own database password and `JWT_SECRET_KEY`. Never commit `.env`.

Run the tests:

```bash
.venv\Scripts\python.exe -m pytest
cd frontend
npm test
```

Loading demo data (`backend/scripts/seed.py`) and the browser tests currently need the M5 files from the capstone project. Removing that dependency is the first milestone.

## Documentation

| Topic | Document |
|---|---|
| Architecture | [docs/28_architecture.md](docs/28_architecture.md) |
| Database | [docs/10_database_design.md](docs/10_database_design.md) |
| Reorder formulas | [docs/06_inventory_engine.md](docs/06_inventory_engine.md) |
| API | [docs/16_api_reference.md](docs/16_api_reference.md), [13](docs/13_inventory_api.md), [14](docs/14_forecast_and_recommendation_api.md), [15](docs/15_purchase_orders_api.md) |
| Security | [docs/12_authentication.md](docs/12_authentication.md) |
| Docker | [docs/29_docker_guide.md](docs/29_docker_guide.md) |

## Licence

All rights reserved © 2026 Prijesh. This is proprietary software intended for commercial use; no licence is granted to copy, modify or distribute it without written permission.
