from __future__ import annotations

import math
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import DbSession, require_roles
from app.db.session import session_factory_dependency
from app.models import RecommendationRun, ReorderRecommendation, User
from app.models.enums import ReviewStatus, RiskCategory, UserRole
from app.schemas.planning import (
    RecommendationOut, RecommendationPage, RecommendationRunCreate, RecommendationRunOut, ReviewIn,
)
from app.services import recommendations as service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
SessionFactory = Annotated[sessionmaker[Session], Depends(session_factory_dependency)]


def run_out(db: Session, run: RecommendationRun) -> RecommendationRunOut:
    out = RecommendationRunOut.model_validate(run)
    out.summary = service.run_summary(db, run.id)
    return out


def rec_out(rec: ReorderRecommendation, sku: str, name: str) -> RecommendationOut:
    data = {c.name: getattr(rec, c.name) for c in rec.__table__.columns}
    data["warnings"] = (rec.warnings or {}).get("messages", [])
    return RecommendationOut(**data, sku=sku, name=name)


@router.post("/runs", response_model=RecommendationRunOut, status_code=status.HTTP_202_ACCEPTED,
             summary="Generate recommendations for all products from a forecast run (manager or admin)")
def start_run(data: RecommendationRunCreate, background: BackgroundTasks, db: DbSession, user: Manager,
              factory: SessionFactory) -> RecommendationRunOut:
    run = service.create_run(db, forecast_run_id=data.forecast_run_id,
                             overrides=data.model_dump(exclude={"forecast_run_id"}), user=user)
    background.add_task(service.execute_run, factory, run.shop_id, run.id)
    return run_out(db, run)


@router.get("/runs", response_model=list[RecommendationRunOut])
def list_runs(db: DbSession, limit: int = Query(50, ge=1, le=200)) -> list[RecommendationRunOut]:
    return [run_out(db, r) for r in service.list_runs(db, limit)]


@router.get("/runs/{run_id}", response_model=RecommendationRunOut)
def get_run(run_id: int, db: DbSession) -> RecommendationRunOut:
    return run_out(db, service.get_run(db, run_id))


@router.get("", response_model=RecommendationPage,
            summary="Recommendations of one run (default: latest completed), filter and sort")
def list_recommendations(
    db: DbSession,
    run_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    risk: RiskCategory | None = None,
    review_status: ReviewStatus | None = None,
    search: str | None = Query(None, max_length=100),
    only_orders: bool = Query(False, description="Only rows with a suggested quantity > 0"),
    sort: Literal["risk", "sku", "suggested_qty", "estimated_order_cost", "days_of_cover"] = "risk",
    order: Literal["asc", "desc"] = "asc",
) -> RecommendationPage:
    run, rows, total = service.list_recommendations(
        db, run_id=run_id, page=page, page_size=page_size, risk=risk, review_status=review_status,
        search=search, only_orders=only_orders, sort=sort, order=order)
    return RecommendationPage(run=run_out(db, run), items=[rec_out(*row) for row in rows], total=total,
                              page=page, page_size=page_size, pages=max(1, math.ceil(total / page_size)))


@router.patch("/{recommendation_id}", response_model=RecommendationOut,
              summary="Approve, reject or reset a recommendation (manager or admin)")
def review(recommendation_id: int, data: ReviewIn, db: DbSession, user: Manager) -> RecommendationOut:
    return rec_out(*service.review(db, recommendation_id, data.review_status, user))
