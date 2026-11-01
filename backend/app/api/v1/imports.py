from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbSession, require_roles
from app.models import User
from app.models.enums import RunStatus, UserRole
from app.services import imports as service

router = APIRouter(prefix="/imports", tags=["data import"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    import_type: str
    status: RunStatus
    rows_total: int
    rows_valid: int
    rows_invalid: int
    errors: dict[str, Any] | None
    created_at: datetime


def mapping(sku_column: str = Form("sku"), date_column: str = Form("date"), units_column: str = Form("units"),
            price_column: str | None = Form("unit_price")) -> service.Mapping:
    """Which CSV column holds each field (form fields next to the file)."""
    return service.Mapping(sku=sku_column.strip(), date=date_column.strip(), units=units_column.strip(),
                           unit_price=(price_column or "").strip() or None)


ColumnMapping = Annotated[service.Mapping, Depends(mapping)]


@router.post("/sales/preview", summary="Check a sales CSV without importing: counts, row errors, first rows")
async def preview_sales(db: DbSession, _: Manager, columns: ColumnMapping,
                        file: UploadFile = File(..., description="CSV with sku, date (YYYY-MM-DD), units[, unit_price]")
                        ) -> dict:
    return service.preview(db, await file.read(), columns)


@router.post("/sales", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED,
             responses={422: {"description": "File has invalid rows; nothing imported (job recorded as failed)"}},
             summary="Import a sales CSV: all rows or none")
async def import_sales(db: DbSession, user: Manager, columns: ColumnMapping, file: UploadFile = File(...)):
    job = service.commit(db, await file.read(), columns, file.filename or "upload.csv", user)
    out = ImportJobOut.model_validate(job)
    if job.status == RunStatus.FAILED:
        return JSONResponse(status_code=422, content={
            "detail": f"{job.rows_invalid} invalid row(s); nothing was imported", **out.model_dump(mode="json")})
    return out


@router.get("/jobs", response_model=list[ImportJobOut], summary="Import history, newest first")
def list_jobs(db: DbSession) -> list:
    return service.list_jobs(db)
