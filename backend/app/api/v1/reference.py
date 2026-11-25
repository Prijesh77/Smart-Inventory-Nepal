"""Categories, suppliers and shelves (lists for filters and forms; adding/editing for managers), and the festival calendar."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require_roles
from app.core.errors import ConflictError, NotFoundError
from app.db.session import get_db
from app.models import Category, Product, Shelf, Supplier, User
from app.models.enums import UserRole
from app.schemas.products import (CategoryCreate, CategoryOut, ShelfCreate, ShelfOut, ShelfUpdate, SupplierCreate,
                                  SupplierOut, SupplierUpdate)
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


def _shelf_out(db: Session, shelf: Shelf) -> ShelfOut:
    count = db.scalar(select(func.count()).select_from(Product)
                      .where(Product.shelf_id == shelf.id, Product.is_active.is_(True))) or 0
    return ShelfOut(id=shelf.id, code=shelf.code, name=shelf.name, area=shelf.area, product_count=count)


def _get_shelf(db: Session, shelf_id: int) -> Shelf:
    shelf = db.get(Shelf, shelf_id)
    if shelf is None:
        raise NotFoundError(f"Shelf {shelf_id} not found")
    return shelf


def _check_code_free(db: Session, code: str, except_id: int | None = None) -> None:
    found = db.scalar(select(Shelf.id).where(Shelf.code == code))
    if found is not None and found != except_id:
        raise ConflictError(f"A shelf with code '{code}' already exists")


@router.get("/shelves", response_model=list[ShelfOut], summary="Shelves in this shop, with how many products each holds")
def list_shelves(db: Session = Depends(get_db)) -> list[ShelfOut]:
    counts = dict(db.execute(select(Product.shelf_id, func.count())
                             .where(Product.is_active.is_(True), Product.shelf_id.is_not(None))
                             .group_by(Product.shelf_id)).all())
    return [ShelfOut(id=s.id, code=s.code, name=s.name, area=s.area, product_count=counts.get(s.id, 0))
            for s in db.scalars(select(Shelf).order_by(Shelf.code))]


@router.post("/shelves", response_model=ShelfOut, status_code=status.HTTP_201_CREATED,
             summary="Add a shelf (manager or admin)")
def create_shelf(data: ShelfCreate, db: DbSession, _: Manager) -> ShelfOut:
    _check_code_free(db, data.code)
    shelf = Shelf(**data.model_dump())
    db.add(shelf)
    db.commit()
    return _shelf_out(db, shelf)


@router.patch("/shelves/{shelf_id}", response_model=ShelfOut, summary="Rename or change a shelf (manager or admin)")
def update_shelf(shelf_id: int, data: ShelfUpdate, db: DbSession, _: Manager) -> ShelfOut:
    shelf = _get_shelf(db, shelf_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("code"):
        _check_code_free(db, changes["code"], except_id=shelf.id)
        shelf.code = changes["code"]
    if (changes.get("name") or "").strip():
        shelf.name = changes["name"].strip()
    if "area" in changes:
        shelf.area = (changes["area"] or "").strip() or None
    db.commit()
    return _shelf_out(db, shelf)


@router.delete("/shelves/{shelf_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a shelf; its products are left without a shelf (manager or admin)")
def delete_shelf(shelf_id: int, db: DbSession, _: Manager) -> None:
    shelf = _get_shelf(db, shelf_id)
    db.execute(update(Product).where(Product.shelf_id == shelf.id).values(shelf_id=None))
    db.delete(shelf)
    db.commit()


@router.get("/festivals", summary="The Nepali festival dates the forecasts use (shared by all shops)")
def list_festivals() -> dict:
    """From ml/calendar/nepal_festivals.json: BS and AD dates, sources, and which dates still need checking."""
    data = json.loads(FESTIVAL_FILE.read_text(encoding="utf-8"))
    return {"covers": data["covers"], "festivals": data["festivals"]}
