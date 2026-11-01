from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import DbSession, require_roles
from app.db.session import session_factory_dependency
from app.models import ForecastRun, User
from app.models.enums import EvaluationPeriod, UserRole
from app.schemas.planning import EvaluationOut, ForecastRunCreate, ForecastRunOut, ProductForecastOut
from app.services import forecasting as service
from app.services import model_training

router = APIRouter(prefix="/forecasts", tags=["forecasts"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
SessionFactory = Annotated[sessionmaker[Session], Depends(session_factory_dependency)]


@router.post("/runs", response_model=ForecastRunOut, status_code=status.HTTP_202_ACCEPTED,
             summary="Start a forecast run in the background (manager or admin). Poll GET /forecasts/runs/{id}.")
def start_run(data: ForecastRunCreate, background: BackgroundTasks, db: DbSession, user: Manager,
              factory: SessionFactory) -> ForecastRun:
    run = service.create_run(db, model_name=data.model_name, horizon_days=data.horizon_days,
                             origin_date=data.origin_date, user=user)
    background.add_task(service.execute_run, factory, run.shop_id, run.id)
    return run


@router.get("/model", summary="This shop's Random Forest: trained or not, history needed, accuracy, what 'auto' uses")
def model_status(db: DbSession) -> dict:
    return model_training.model_status(db)


@router.post("/model/train", status_code=status.HTTP_202_ACCEPTED,
             summary="(Re)train this shop's Random Forest in the background (manager or admin). Poll GET /forecasts/model.",
             responses={409: {"description": "Already training, or not enough sales history yet"}})
def train_model(background: BackgroundTasks, db: DbSession, _: Manager, factory: SessionFactory) -> dict:
    shop_id = model_training.start_training(db)
    background.add_task(model_training.train_in_background, factory, shop_id)
    return {"training": True}


@router.get("/runs", response_model=list[ForecastRunOut], summary="Forecast runs, newest first")
def list_runs(db: DbSession, limit: int = Query(50, ge=1, le=200)) -> list[ForecastRun]:
    return service.list_runs(db, limit)


@router.get("/runs/{run_id}", response_model=ForecastRunOut)
def get_run(run_id: int, db: DbSession) -> ForecastRun:
    return service.get_run(db, run_id)


@router.get("/products/{product_id}", response_model=ProductForecastOut,
            summary="Actual sales history and forecast for one product (default: latest completed run)")
def product_forecast(product_id: int, db: DbSession, run_id: int | None = None,
                     history_days: int = Query(56, ge=7, le=365)) -> dict:
    return service.product_forecast(db, product_id, run_id, history_days)


@router.get("/evaluations", response_model=list[EvaluationOut],
            summary="Backtest accuracy of each model (Phase 3): MAE, RMSE, WAPE, bias by demand class")
def evaluations(db: DbSession, period: EvaluationPeriod | None = None,
                horizon_days: int | None = Query(None, ge=1, le=90)) -> list:
    return service.evaluations(db, period, horizon_days)
