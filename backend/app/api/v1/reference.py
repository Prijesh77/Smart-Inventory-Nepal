"""Categories and suppliers (lists for filters and forms; adding/editing for managers), and the festival calendar."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.db.session import get_db
from app.models import Category, Supplier, User
from app.models.enums import UserRole
from app.schemas.products import CategoryCreate, CategoryOut, SupplierCreate, SupplierOut, SupplierUpdate
from app.services.imports import category_code
from ml.calendar.festivals import DATA_FILE as FESTIVAL_FILE

router = APIRouter(tags=["reference data"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.code)))


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED,
             summary="Add a category (manager or admin)")
def create_category(data: CategoryCreate, db: DbSession, _: Manager) -> Category:
    code = (data.code or category_code(data.name)).upper()
    if db.scalar(select(Category.id).where(Category.code == code)) is not None:
        raise ConflictError(f"A category with code '{code}' already exists")
    category = Category(code=code, name=data.name)
    db.add(category)
    db.commit()
    return category


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db)) -> list[Supplier]:
    return list(db.scalars(select(Supplier).order_by(Supplier.code)))


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED,
             summary="Add a supplier (manager or admin)")
def create_supplier(data: SupplierCreate, db: DbSession, _: Manager) -> Supplier:
    if db.scalar(select(Supplier.id).where(Supplier.code == data.code)) is not None:
        raise ConflictError(f"A supplier with code '{data.code}' already exists")
    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    db.commit()
    return supplier


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut, summary="Edit a supplier (manager or admin)")
def update_supplier(supplier_id: int, data: SupplierUpdate, db: DbSession, _: Manager) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFoundError(f"Supplier {supplier_id} not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(supplier, key, value)
    db.commit()
    return supplier


@router.get("/festivals", summary="The Nepali festival dates the forecasts use (shared by all shops)")
def list_festivals() -> dict:
    """From ml/calendar/nepal_festivals.json: BS and AD dates, sources, and which dates still need checking."""
    data = json.loads(FESTIVAL_FILE.read_text(encoding="utf-8"))
    return {"covers": data["covers"], "festivals": data["festivals"]}
