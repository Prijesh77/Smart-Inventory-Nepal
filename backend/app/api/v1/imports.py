from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse, Response
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
    """Sales imports only: which file column holds each field (form fields next to the file)."""
    return service.Mapping(sku=sku_column.strip(), date=date_column.strip(), units=units_column.strip(),
                           unit_price=(price_column or "").strip() or None)


ColumnMapping = Annotated[service.Mapping, Depends(mapping)]


ImportType = Literal["suppliers", "products", "opening_stock", "sales"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/types", summary="The import types, their columns and what each column means")
def import_types() -> list[dict]:
    return service.types_out()


@router.get("/templates/{import_type}.xlsx", summary="Download an Excel template with example rows and instructions",
            response_class=Response, responses={200: {"content": {XLSX: {}}}})
def template(import_type: ImportType) -> Response:
    return Response(service.template_xlsx(import_type), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{import_type}_template.xlsx"'})


@router.post("/{import_type}/preview",
             summary="Check an Excel (.xlsx) or CSV file without importing: counts, row errors, first rows")
async def preview(import_type: ImportType, db: DbSession, _: Manager, columns: ColumnMapping,
                  file: UploadFile = File(..., description="Excel .xlsx or UTF-8 CSV with the template's columns")
                  ) -> dict:
    return service.preview(db, import_type, await file.read(), file.filename or "upload", columns)


@router.post("/{import_type}", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED,
             responses={422: {"description": "File has invalid rows; nothing imported (job recorded as failed)"}},
             summary="Import an Excel or CSV file: all rows or none")
async def run_import(import_type: ImportType, db: DbSession, user: Manager, columns: ColumnMapping,
                     file: UploadFile = File(...)):
    job = service.commit(db, import_type, await file.read(), file.filename or "upload", user, columns)
    out = ImportJobOut.model_validate(job)
    if job.status == RunStatus.FAILED:
        return JSONResponse(status_code=422, content={
            "detail": f"{job.rows_invalid} invalid row(s); nothing was imported", **out.model_dump(mode="json")})
    return out


@router.get("/jobs", response_model=list[ImportJobOut], summary="Import history, newest first")
def list_jobs(db: DbSession) -> list:
    return service.list_jobs(db)
