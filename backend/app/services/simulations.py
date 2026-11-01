"""Run the Phase 4 inventory simulation from the app.

This runs the research experiment (ml/experiments/run_simulation.py) on the
research data set: the 267 sampled items over the test year, with real M5
demand and SIMULATED stock, costs and lead times. It compares the textbook
baseline, the engine with MA-28 forecasts and the engine with the Random
Forest, with the user's chosen costs and service levels. Results are
SIMULATED by definition and stored with the run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import NotFoundError
from app.models import SimulationRun, User
from app.models.enums import RunStatus

logger = logging.getLogger("app.simulations")
NOTE = ("SIMULATED results: real M5 demand (store CA_1, 267 items, test year 2015-05-25..2016-05-22); "
        "stock, costs and lead times are generated assumptions. Unmet demand = lost sale.")


def create(db: Session, *, name: str, params: dict[str, Any], user: User) -> SimulationRun:
    run = SimulationRun(name=name, params=params, status=RunStatus.PENDING, created_by=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _clean(value):
    """JSON-safe numbers (NaN -> None)."""
    if isinstance(value, (float, np.floating)):
        return None if np.isnan(value) else round(float(value), 6)
    if isinstance(value, np.integer):
        return int(value)
    return value


def execute(session_factory: sessionmaker[Session], run_id: int) -> None:
    # Imported here: loading the research stack is only needed when a simulation actually runs.
    from ml.data.inspect_m5 import Report
    from ml.evaluation.inventory_compare import matched_difference
    from ml.experiments.run_simulation import POLICIES, prepare, run_policy, summarize
    from ml.inventory.simulation import CostSettings

    with session_factory() as db:
        run = db.get(SimulationRun, run_id)
        run.status = RunStatus.RUNNING
        db.commit()
        p = run.params
        try:
            ctx = prepare(Report())
            costs = CostSettings(ordering_cost=p["ordering_cost"], holding_cost_rate=p["holding_cost_rate"])
            import pandas as pd
            runs = pd.concat([run_policy(ctx, pol, sl, costs, p["uncertain_lead_time"])
                              for pol in POLICIES for sl in p["service_levels"]], ignore_index=True)
            summary = summarize(runs)
            cols = ["policy", "service_level", "demand_class", "fill_rate", "stockout_rate", "units_lost",
                    "avg_inventory_value", "n_orders", "holding_cost", "ordering_cost", "total_cost", "lost_margin"]
            table = [{k: _clean(v) for k, v in row.items()} for row in summary[cols].to_dict("records")]
            allc = summary[summary["demand_class"] == "all"]
            matched = []
            if len(p["service_levels"]) >= 2:
                for pol, ref in [("engine_rf", "baseline_demand_sd"), ("engine_rf", "engine_ma28"),
                                 ("engine_ma28", "baseline_demand_sd")]:
                    m = matched_difference(allc, pol, ref)
                    matched.append({"policy": pol, "reference": ref, **{k: _clean(v) for k, v in m.items()}})
            run.results = {"note": NOTE, "summary": table, "matched_comparisons": matched,
                           "items": int(len(ctx.params)), "days": int(ctx.demand.shape[1])}
            run.status = RunStatus.COMPLETED
        except FileNotFoundError as exc:
            db.rollback()
            run = db.get(SimulationRun, run_id)
            run.status = RunStatus.FAILED
            run.error_message = f"Research files missing ({exc.filename}); run the Phase 2-4 scripts first"
        except Exception as exc:
            logger.exception("Simulation run %s failed", run_id)
            db.rollback()
            run = db.get(SimulationRun, run_id)
            run.status, run.error_message = RunStatus.FAILED, f"Unexpected error: {type(exc).__name__}"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()


def get(db: Session, run_id: int) -> SimulationRun:
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise NotFoundError(f"Simulation run {run_id} not found")
    return run


def list_runs(db: Session, limit: int = 50) -> list[SimulationRun]:
    return list(db.scalars(select(SimulationRun).order_by(SimulationRun.id.desc()).limit(limit)))
