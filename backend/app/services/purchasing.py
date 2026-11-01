"""Purchase orders: drafts (manual or from approved recommendations), submit, receive, cancel.

Status flow:   draft -> submitted -> partially_received -> received
                 |          |
                 +----------+--> cancelled   (only before anything is received)

"Submitting" only marks the order as placed in this app. The system never
contacts a supplier. Receiving adds stock through inventory.apply_movement,
so every received unit has an audit record linked to its purchase order.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, ConflictError, InvalidReferenceError, NotFoundError
from app.models import (
    DailySales, Product, PurchaseOrder, PurchaseOrderItem, RecommendationRun, ReorderRecommendation, Supplier, User,
)
from app.models.enums import PurchaseOrderStatus, ReviewStatus, RunStatus, TransactionType
from app.services.inventory import apply_movement

Status = PurchaseOrderStatus


def app_today(db: Session) -> date:
    """The app works on historical data: 'today' is the day after the last sales day."""
    last = db.scalar(select(func.max(DailySales.sales_date)))
    return (last + timedelta(days=1)) if last else date.today()


def _load(db: Session, po_id: int, lock: bool = False) -> PurchaseOrder:
    query = select(PurchaseOrder).where(PurchaseOrder.id == po_id).options(selectinload(PurchaseOrder.items))
    po = db.scalar(query.with_for_update() if lock else query)
    if po is None:
        raise NotFoundError(f"Purchase order {po_id} not found")
    return po


def _new_po(db: Session, supplier_id: int, user: User, notes: str | None, expected: date | None) -> PurchaseOrder:
    # A temporary unique number, replaced by the shop's next number (PO-000001, PO-000002, ...) once saved.
    # Numbers count this shop's orders only, so they never reveal how many orders other shops have.
    po = PurchaseOrder(po_number=f"TMP-{uuid.uuid4().hex[:20]}", supplier_id=supplier_id, status=Status.DRAFT,
                       notes=notes, expected_date=expected, created_by=user.id)
    db.add(po)
    db.flush()
    po.po_number = f"PO-{db.scalar(select(func.count()).select_from(PurchaseOrder)):06d}"
    return po


def _check_lines(db: Session, supplier_id: int, lines: list[dict]) -> dict[int, Product]:
    if not lines:
        raise AppError("A purchase order needs at least one line")
    product_ids = [line["product_id"] for line in lines]
    if len(set(product_ids)) != len(product_ids):
        raise AppError("Each product may appear only once per purchase order")
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
    for pid in product_ids:
        product = products.get(pid)
        if product is None:
            raise InvalidReferenceError(f"Unknown product id {pid}")
        if product.supplier_id != supplier_id:
            raise InvalidReferenceError(f"Product {product.sku} is not supplied by supplier {supplier_id}")
    return products


def _add_lines(po: PurchaseOrder, lines: list[dict], products: dict[int, Product]) -> None:
    for line in lines:
        cost = line.get("unit_cost")
        po.items.append(PurchaseOrderItem(
            product_id=line["product_id"], quantity_ordered=line["quantity"],
            unit_cost=cost if cost is not None else products[line["product_id"]].unit_cost,
            recommendation_id=line.get("recommendation_id")))


# ---------------------------------------------------------------- create

def create_draft(db: Session, *, supplier_id: int, lines: list[dict], notes: str | None,
                 expected_date: date | None, user: User) -> PurchaseOrder:
    if db.get(Supplier, supplier_id) is None:
        raise InvalidReferenceError(f"Unknown supplier id {supplier_id}")
    products = _check_lines(db, supplier_id, lines)
    po = _new_po(db, supplier_id, user, notes, expected_date)
    _add_lines(po, lines, products)
    db.commit()
    return _load(db, po.id)


def drafts_from_recommendations(db: Session, *, recommendation_ids: list[int] | None, user: User) -> list[PurchaseOrder]:
    """One draft PO per supplier from APPROVED recommendations, all in one transaction.

    Default: every approved recommendation of the latest completed run.
    The recommendations are marked 'ordered' so they cannot be ordered twice.
    """
    query = (select(ReorderRecommendation).where(ReorderRecommendation.review_status == ReviewStatus.APPROVED)
             .with_for_update())
    if recommendation_ids:
        query = query.where(ReorderRecommendation.id.in_(recommendation_ids))
    else:
        latest = db.scalar(select(RecommendationRun.id).where(RecommendationRun.status == RunStatus.COMPLETED)
                           .order_by(RecommendationRun.id.desc()).limit(1))
        query = query.where(ReorderRecommendation.recommendation_run_id == latest)
    recs = list(db.scalars(query))
    if recommendation_ids and len(recs) != len(set(recommendation_ids)):
        raise ConflictError("Some recommendations are not approved (or already ordered)")
    recs = [r for r in recs if r.suggested_qty > 0]
    if not recs:
        raise NotFoundError("No approved recommendations to order")

    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_([r.product_id for r in recs])))}
    by_supplier: dict[int, list[ReorderRecommendation]] = {}
    for rec in recs:
        supplier_id = products[rec.product_id].supplier_id
        if supplier_id is None:
            raise AppError(f"Product {products[rec.product_id].sku} has no supplier")
        by_supplier.setdefault(supplier_id, []).append(rec)

    today = app_today(db)
    created = []
    for supplier_id, group in sorted(by_supplier.items()):
        lead = db.get(Supplier, supplier_id).lead_time_days
        po = _new_po(db, supplier_id, user, notes="Draft created from approved reorder recommendations",
                     expected=today + timedelta(days=lead))
        _add_lines(po, [{"product_id": r.product_id, "quantity": r.suggested_qty, "recommendation_id": r.id}
                        for r in group], products)
        for rec in group:
            rec.review_status = ReviewStatus.ORDERED
        created.append(po.id)
    db.commit()
    return [_load(db, po_id) for po_id in created]


# ---------------------------------------------------------------- change status

def update_draft(db: Session, po_id: int, *, notes: str | None, expected_date: date | None,
                 lines: list[dict] | None, fields_set: set[str]) -> PurchaseOrder:
    po = _load(db, po_id, lock=True)
    if po.status != Status.DRAFT:
        raise ConflictError(f"Only draft orders can be edited (this one is {po.status.value})")
    if "notes" in fields_set:
        po.notes = notes
    if "expected_date" in fields_set:
        po.expected_date = expected_date
    if lines is not None:
        products = _check_lines(db, po.supplier_id, lines)
        po.items.clear()
        db.flush()
        _add_lines(po, lines, products)
    db.commit()
    return _load(db, po_id)


def submit(db: Session, po_id: int) -> PurchaseOrder:
    po = _load(db, po_id, lock=True)
    if po.status != Status.DRAFT:
        raise ConflictError(f"Only draft orders can be submitted (this one is {po.status.value})")
    if not po.items:
        raise AppError("Cannot submit an empty order")
    po.status = Status.SUBMITTED
    po.submitted_at = datetime.now(timezone.utc)
    if po.expected_date is None:
        po.expected_date = app_today(db) + timedelta(days=db.get(Supplier, po.supplier_id).lead_time_days)
    db.commit()
    return _load(db, po_id)


def receive(db: Session, po_id: int, lines: list[dict], user: User) -> PurchaseOrder:
    """Book delivered quantities into stock. All lines succeed or none do."""
    po = _load(db, po_id, lock=True)
    if po.status not in (Status.SUBMITTED, Status.PARTIALLY_RECEIVED):
        raise ConflictError(f"Only submitted orders can be received (this one is {po.status.value})")
    items = {item.id: item for item in po.items}
    try:
        for line in lines:
            item = items.get(line["item_id"])
            if item is None:
                raise InvalidReferenceError(f"Line {line['item_id']} is not on {po.po_number}")
            remaining = item.quantity_ordered - item.quantity_received
            if line["quantity"] > remaining:
                raise ConflictError(f"Line {item.id}: only {remaining} units still expected")
            item.quantity_received += line["quantity"]
            apply_movement(db, product_id=item.product_id, quantity=line["quantity"],
                           txn_type=TransactionType.RECEIPT, reason=f"Received on {po.po_number}",
                           user=user, purchase_order_id=po.id)
        complete = all(i.quantity_received == i.quantity_ordered for i in po.items)
        po.status = Status.RECEIVED if complete else Status.PARTIALLY_RECEIVED
        if complete:
            po.received_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _load(db, po_id)


def cancel(db: Session, po_id: int) -> PurchaseOrder:
    po = _load(db, po_id, lock=True)
    if po.status not in (Status.DRAFT, Status.SUBMITTED):
        raise ConflictError(f"A {po.status.value} order cannot be cancelled")
    if any(i.quantity_received for i in po.items):
        raise ConflictError("Part of this order was received; it cannot be cancelled")
    po.status = Status.CANCELLED
    # Put the linked recommendations back to 'approved' so they can be ordered again.
    for item in po.items:
        if item.recommendation_id:
            rec = db.get(ReorderRecommendation, item.recommendation_id)
            if rec and rec.review_status == ReviewStatus.ORDERED:
                rec.review_status = ReviewStatus.APPROVED
    db.commit()
    return _load(db, po_id)


# ---------------------------------------------------------------- read

def get(db: Session, po_id: int) -> PurchaseOrder:
    return _load(db, po_id)


def list_orders(db: Session, *, page: int, page_size: int, status: Status | None,
                supplier_id: int | None) -> tuple[list[PurchaseOrder], int]:
    query = select(PurchaseOrder).options(selectinload(PurchaseOrder.items))
    if status:
        query = query.where(PurchaseOrder.status == status)
    if supplier_id:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(PurchaseOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), total or 0


def line_details(db: Session, pos: list[PurchaseOrder]) -> dict:
    """SKU/name per product and supplier code/name, for building responses."""
    product_ids = {i.product_id for po in pos for i in po.items}
    supplier_ids = {po.supplier_id for po in pos}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))} if product_ids else {}
    suppliers = {s.id: s for s in db.scalars(select(Supplier).where(Supplier.id.in_(supplier_ids)))}
    return {"products": products, "suppliers": suppliers}


def line_total(quantity: int, unit_cost: Decimal | None) -> Decimal | None:
    return None if unit_cost is None else (unit_cost * quantity).quantize(Decimal("0.01"))
