from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import DbSession, require_roles
from app.db.session import session_factory_dependency
from app.models import SimulationRun, User
from app.models.enums import RunStatus, UserRole
from app.services import simulations as service

router = APIRouter(prefix="/simulations", tags=["simulations (SIMULATED results)"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
SessionFactory = Annotated[sessionmaker[Session], Depends(session_factory_dependency)]
ServiceLevel = Literal[0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99]


class SimulationCreate(BaseModel):
    name: str = Field("Policy comparison", min_length=1, max_length=120)
    service_levels: list[ServiceLevel] = Field(default_factory=lambda: [0.8, 0.9, 0.95, 0.98],
                                               min_length=1, max_length=7)
    ordering_cost: float = Field(10.0, ge=0, le=1000)
    holding_cost_rate: float = Field(0.25, ge=0.01, le=1)
    uncertain_lead_time: bool = Field(False, description="Real lead times vary around the supplier mean")


class SimulationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    status: RunStatus
    params: dict[str, Any]
    results: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


@router.post("", response_model=SimulationOut, status_code=status.HTTP_202_ACCEPTED,
             summary="Start a simulation in the background (about 10-30 s); poll GET /simulations/{id}")
def start(data: SimulationCreate, background: BackgroundTasks, db: DbSession, user: Manager,
          factory: SessionFactory) -> SimulationRun:
    params = data.model_dump(exclude={"name"})
    params["service_levels"] = sorted(set(params["service_levels"]))
    run = service.create(db, name=data.name, params=params, user=user)
    background.add_task(service.execute, factory, run.shop_id, run.id)
    return run


@router.get("", response_model=list[SimulationOut])
def list_runs(db: DbSession, limit: int = Query(50, ge=1, le=200)) -> list[SimulationRun]:
    return service.list_runs(db, limit)


@router.get("/{run_id}", response_model=SimulationOut)
def get_run(run_id: int, db: DbSession) -> SimulationRun:
    return service.get(db, run_id)
