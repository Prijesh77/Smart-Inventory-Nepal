from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import RequireManager
from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.products import ProductCreate, ProductOut, ProductUpdate, SalesHistory
from app.services import products as service

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[ProductOut], summary="List, search, filter and sort products")
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=100, description="Matches SKU or name"),
    category: str | None = Query(None, description="Category code, e.g. FOODS"),
    supplier_id: int | None = None,
    demand_class: str | None = Query(None, description="smooth, erratic, intermittent or lumpy"),
    is_active: bool | None = None,
    sort: service.SortField = "sku",
    order: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
) -> Page[ProductOut]:
    items, total = service.list_products(
        db, page=page, page_size=page_size, search=search, category=category, supplier_id=supplier_id,
        demand_class=demand_class, is_active=is_active, sort=sort, order=order,
    )
    return Page.build(items, total, page, page_size)


@router.get("/{product_id}", response_model=ProductOut, summary="One product with its current stock")
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductOut:
    return service.get_product(db, product_id)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED, dependencies=[RequireManager],
             summary="Create a product (409 if the SKU exists). Manager or admin.")
def create_product(data: ProductCreate, db: Session = Depends(get_db)) -> ProductOut:
    return service.create_product(db, data)


@router.patch("/{product_id}", response_model=ProductOut, dependencies=[RequireManager],
              summary="Change some fields of a product. Manager or admin.")
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)) -> ProductOut:
    return service.update_product(db, product_id, data)


@router.get("/{product_id}/sales", response_model=SalesHistory,
            summary="Daily sales history (default: last 90 days of data)")
def sales_history(product_id: int, start: date | None = None, end: date | None = None,
                  db: Session = Depends(get_db)) -> SalesHistory:
    return service.sales_history(db, product_id, start, end)
