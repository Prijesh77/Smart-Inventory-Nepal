"""Product queries and changes."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ConflictError, InvalidReferenceError, NotFoundError
from app.models import Category, DailySales, InventoryBalance, Product, Supplier
from app.schemas.products import ProductCreate, ProductOut, ProductUpdate, SalesHistory, SalesPoint

SORT_COLUMNS = {
    "sku": Product.sku,
    "name": Product.name,
    "unit_price": Product.unit_price,
    "on_hand": func.coalesce(InventoryBalance.on_hand, 0),
    "created_at": Product.created_at,
}
SortField = Literal["sku", "name", "unit_price", "on_hand", "created_at"]


def to_out(product: Product, on_hand: int | None) -> ProductOut:
    return ProductOut(
        id=product.id, sku=product.sku, name=product.name, category=product.category,
        department=product.department, supplier=product.supplier, unit_price=product.unit_price,
        unit_cost=product.unit_cost, lead_time_days=product.lead_time_days,
        effective_lead_time_days=product.effective_lead_time_days, min_order_qty=product.min_order_qty,
        pack_size=product.pack_size, demand_class=product.demand_class, is_active=product.is_active,
        on_hand=on_hand or 0, created_at=product.created_at, updated_at=product.updated_at,
    )


def _base_query() -> Select:
    return (
        select(Product, InventoryBalance.on_hand)
        .outerjoin(InventoryBalance, InventoryBalance.product_id == Product.id)
        .join(Category, Category.id == Product.category_id)
        .options(joinedload(Product.category), joinedload(Product.supplier))
    )


def list_products(
    db: Session, *, page: int, page_size: int, search: str | None = None, category: str | None = None,
    supplier_id: int | None = None, demand_class: str | None = None, is_active: bool | None = None,
    sort: SortField = "sku", order: Literal["asc", "desc"] = "asc",
) -> tuple[list[ProductOut], int]:
    query = _base_query()
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Product.sku.ilike(pattern), Product.name.ilike(pattern)))
    if category:
        query = query.where(Category.code == category.upper())
    if supplier_id is not None:
        query = query.where(Product.supplier_id == supplier_id)
    if demand_class:
        query = query.where(Product.demand_class == demand_class)
    if is_active is not None:
        query = query.where(Product.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    column = SORT_COLUMNS[sort]
    query = query.order_by(column.desc() if order == "desc" else column.asc(), Product.id)
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return [to_out(p, on_hand) for p, on_hand in rows], total or 0


def get_product(db: Session, product_id: int) -> ProductOut:
    row = db.execute(_base_query().where(Product.id == product_id)).unique().first()
    if row is None:
        raise NotFoundError(f"Product {product_id} not found")
    return to_out(*row)


def _category_id(db: Session, code: str) -> int:
    category_id = db.scalar(select(Category.id).where(Category.code == code.upper()))
    if category_id is None:
        raise InvalidReferenceError(f"Unknown category code '{code}'")
    return category_id


def _check_supplier(db: Session, supplier_id: int | None) -> None:
    if supplier_id is not None and db.get(Supplier, supplier_id) is None:
        raise InvalidReferenceError(f"Unknown supplier id {supplier_id}")


def create_product(db: Session, data: ProductCreate) -> ProductOut:
    """Create a product and its (empty) stock balance in one transaction."""
    if db.scalar(select(Product.id).where(Product.sku == data.sku)) is not None:
        raise ConflictError(f"A product with SKU '{data.sku}' already exists")
    _check_supplier(db, data.supplier_id)
    fields = data.model_dump(exclude={"category_code"})
    product = Product(**fields, category_id=_category_id(db, data.category_code))
    db.add(product)
    db.flush()
    db.add(InventoryBalance(product_id=product.id, on_hand=0, backorders=0))
    db.commit()
    return get_product(db, product.id)


def update_product(db: Session, product_id: int, data: ProductUpdate) -> ProductOut:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    changes = data.model_dump(exclude_unset=True)
    if "category_code" in changes:
        product.category_id = _category_id(db, changes.pop("category_code"))
    if "supplier_id" in changes:
        _check_supplier(db, changes["supplier_id"])
    for field, value in changes.items():
        setattr(product, field, value)
    db.commit()
    db.expire_all()
    return get_product(db, product_id)


def sales_history(db: Session, product_id: int, start: date | None, end: date | None) -> SalesHistory:
    """Daily sales for one product. Defaults to the last 90 days that have data."""
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Product {product_id} not found")
    if end is None:
        end = db.scalar(select(func.max(DailySales.sales_date)).where(DailySales.product_id == product_id))
        end = end or date.today()
    start = start or end - timedelta(days=89)
    if start > end:
        raise InvalidReferenceError("start must be on or before end")
    rows = db.scalars(
        select(DailySales).where(DailySales.product_id == product_id,
                                 DailySales.sales_date.between(start, end)).order_by(DailySales.sales_date)
    ).all()
    points = [SalesPoint.model_validate(r) for r in rows]
    return SalesHistory(product_id=product_id, sku=product.sku, start=start, end=end,
                        total_units=sum(p.units for p in points), points=points)
