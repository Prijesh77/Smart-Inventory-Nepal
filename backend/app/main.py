"""FastAPI application.

Run from the backend folder:
    ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload
Interactive API docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.errors import register_error_handlers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Inventory and Reorder Recommendation API",
        version="0.1.0",
        description=(
            "Demand forecasting and explainable reorder recommendations for retail inventory. "
            "Sales are real M5 data (store CA_1); stock levels, costs and lead times are SIMULATED."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],   # Vite dev server (Phase 6)
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(v1_router)
    return app


app = create_app()
