"""Overview metrics (Page 1) and analytics (Page 6)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.services import dashboard as service

router = APIRouter(tags=["dashboard & analytics"])


@router.get("/dashboard/summary", summary="All overview figures, computed live. "
                                          "Fields listed in simulated_fields depend on SIMULATED inputs.")
def dashboard_summary(db: DbSession) -> dict:
    return service.summary(db)


@router.get("/analytics/sales-trend", summary="Units and revenue per day")
def sales_trend(db: DbSession, days: int = Query(90, ge=7, le=730), category: str | None = None,
                product_id: int | None = None) -> list[dict]:
    return service.sales_trend(db, days, category, product_id)


@router.get("/analytics/weekly-trend", summary="Units per week per category")
def weekly_trend(db: DbSession, weeks: int = Query(26, ge=4, le=260), category: str | None = None) -> list[dict]:
    return service.weekly_trend(db, weeks, category)


@router.get("/analytics/categories", summary="Sales, stock and days of cover per category")
def categories(db: DbSession, days: int = Query(28, ge=7, le=365)) -> list[dict]:
    return service.category_performance(db, days)


@router.get("/analytics/slow-movers", summary="Stock that has not sold for `days` days, and the money tied up in it")
def slow_movers(db: DbSession, days: int = Query(60, ge=7, le=365)) -> dict:
    return service.slow_movers(db, days)
