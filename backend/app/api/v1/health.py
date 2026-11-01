from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", summary="API and database status")
def health(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:   # report, never crash, on a health check
        database = "unavailable"
    status_code = 200 if database == "ok" else 503
    return JSONResponse(status_code=status_code, content={"status": "ok" if status_code == 200 else "degraded",
                                                          "database": database})
