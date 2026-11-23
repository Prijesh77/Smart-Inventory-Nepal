from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.sales import SalesCoverageOut, SalesDayOut, SalesEntryIn
from app.services import sales as service

router = APIRouter(prefix="/sales", tags=["sales"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


@router.get("", response_model=SalesDayOut, summary="Sales recorded for one day (default: today)")
def sales_for_day(db: DbSession, day: date | None = Query(None, alias="date")) -> SalesDayOut:
    return SalesDayOut(**service.day_summary(db, day or date.today()))


@router.get("/coverage", response_model=SalesCoverageOut,
            summary="How complete the last 28 days of sales records are (days missing or only partly entered)")
def sales_coverage(db: DbSession) -> SalesCoverageOut:
    return SalesCoverageOut(**service.coverage(db))


@router.post("", response_model=SalesDayOut, status_code=status.HTTP_201_CREATED,
             summary="Record units sold on a day: adds to the day's sales and takes them out of stock (manager or admin)")
def record_sales(data: SalesEntryIn, db: DbSession, user: Manager) -> SalesDayOut:
    result = service.record_sales(db, day=data.sales_date, items=[(i.product_id, i.units) for i in data.items],
                                  close_day=data.close_day, user=user)
    return SalesDayOut(**result)
