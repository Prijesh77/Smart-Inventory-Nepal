from __future__ import annotations

import math
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require_roles
from app.models import PurchaseOrder, User
from app.models.enums import PurchaseOrderStatus, UserRole
from app.schemas.purchasing import (
    FromRecommendationsIn, LineOut, PurchaseOrderCreate, PurchaseOrderOut, PurchaseOrderPage, PurchaseOrderUpdate,
    ReceiveIn,
)
from app.services import purchasing as service

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])
Manager = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


def to_out(db: Session, pos: list[PurchaseOrder]) -> list[PurchaseOrderOut]:
    details = service.line_details(db, pos)
    out = []
    for po in pos:
        lines = []
        for item in sorted(po.items, key=lambda i: i.id):
            product = details["products"][item.product_id]
            lines.append(LineOut(
                id=item.id, product_id=item.product_id, sku=product.sku, name=product.name,
                quantity_ordered=item.quantity_ordered, quantity_received=item.quantity_received,
                quantity_outstanding=item.quantity_ordered - item.quantity_received, unit_cost=item.unit_cost,
                line_total=service.line_total(item.quantity_ordered, item.unit_cost),
                recommendation_id=item.recommendation_id))
        supplier = details["suppliers"][po.supplier_id]
        out.append(PurchaseOrderOut(
            id=po.id, po_number=po.po_number, supplier_id=po.supplier_id, supplier_code=supplier.code,
            supplier_name=supplier.name, status=po.status, expected_date=po.expected_date,
            submitted_at=po.submitted_at, received_at=po.received_at, notes=po.notes, created_at=po.created_at,
            lines=lines, total_units=sum(line.quantity_ordered for line in lines),
            total_cost=sum((line.line_total or Decimal(0) for line in lines), Decimal("0.00"))))
    return out


@router.get("", response_model=PurchaseOrderPage, summary="Purchase orders, newest first")
def list_orders(db: DbSession, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                status_filter: PurchaseOrderStatus | None = Query(None, alias="status"),
                supplier_id: int | None = None) -> PurchaseOrderPage:
    pos, total = service.list_orders(db, page=page, page_size=page_size, status=status_filter, supplier_id=supplier_id)
    return PurchaseOrderPage(items=to_out(db, pos), total=total, page=page, page_size=page_size,
                             pages=max(1, math.ceil(total / page_size)))


@router.get("/{po_id}", response_model=PurchaseOrderOut)
def get_order(po_id: int, db: DbSession) -> PurchaseOrderOut:
    return to_out(db, [service.get(db, po_id)])[0]


@router.post("", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED,
             summary="Create a draft order by hand (manager or admin)")
def create_order(data: PurchaseOrderCreate, db: DbSession, user: Manager) -> PurchaseOrderOut:
    po = service.create_draft(db, supplier_id=data.supplier_id, lines=[line.model_dump() for line in data.lines],
                              notes=data.notes, expected_date=data.expected_date, user=user)
    return to_out(db, [po])[0]


@router.post("/from-recommendations", response_model=list[PurchaseOrderOut], status_code=status.HTTP_201_CREATED,
             summary="Draft orders (one per supplier) from APPROVED recommendations (manager or admin)")
def from_recommendations(data: FromRecommendationsIn, db: DbSession, user: Manager) -> list[PurchaseOrderOut]:
    return to_out(db, service.drafts_from_recommendations(db, recommendation_ids=data.recommendation_ids, user=user))


@router.patch("/{po_id}", response_model=PurchaseOrderOut, summary="Edit a draft order (manager or admin)")
def update_order(po_id: int, data: PurchaseOrderUpdate, db: DbSession, _: Manager) -> PurchaseOrderOut:
    lines = [line.model_dump() for line in data.lines] if data.lines is not None else None
    po = service.update_draft(db, po_id, notes=data.notes, expected_date=data.expected_date, lines=lines,
                              fields_set=data.model_fields_set)
    return to_out(db, [po])[0]


@router.post("/{po_id}/submit", response_model=PurchaseOrderOut,
             summary="Mark a draft as placed (nothing is sent to the supplier)")
def submit_order(po_id: int, db: DbSession, _: Manager) -> PurchaseOrderOut:
    return to_out(db, [service.submit(db, po_id)])[0]


@router.post("/{po_id}/receive", response_model=PurchaseOrderOut,
             summary="Book delivered quantities into stock (creates receipt transactions)")
def receive_order(po_id: int, data: ReceiveIn, db: DbSession, user: Manager) -> PurchaseOrderOut:
    return to_out(db, [service.receive(db, po_id, [line.model_dump() for line in data.lines], user)])[0]


@router.post("/{po_id}/cancel", response_model=PurchaseOrderOut,
             summary="Cancel a draft or submitted order with nothing received")
def cancel_order(po_id: int, db: DbSession, _: Manager) -> PurchaseOrderOut:
    return to_out(db, [service.cancel(db, po_id)])[0]
