"""The database itself must reject invalid data, even if the API has a bug."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.base import Base
from app.models import (
    Category, DailySales, CalendarDay, InventoryBalance, InventoryTransaction, Product,
    PurchaseOrder, PurchaseOrderItem, ReorderRecommendation, RecommendationRun, Supplier,
)
from app.models.enums import PurchaseOrderStatus, RiskCategory, TransactionType


def make_product(db, sku: str = "FOODS_3_001", **overrides) -> Product:
    category = db.scalar(select(Category).where(Category.code == "FOODS")) or Category(code="FOODS", name="Foods")
    supplier = db.scalar(select(Supplier).where(Supplier.code == "SUP_B")) or Supplier(
        code="SUP_B", name="Supplier B", lead_time_days=5, lead_time_sd_days=Decimal("1.0"))
    fields = {"sku": sku, "name": "Example", "category": category, "supplier": supplier,
              "unit_price": Decimal("3.50"), "unit_cost": Decimal("2.30"), "pack_size": 6, "min_order_qty": 6}
    product = Product(**{**fields, **overrides})
    db.add(product)
    db.flush()
    return product


def test_all_tables_created():
    assert len(Base.metadata.tables) == 18


def test_duplicate_sku_rejected(db):
    make_product(db)
    with pytest.raises(IntegrityError):
        make_product(db)


@pytest.mark.parametrize("field, value", [
    ("pack_size", 0), ("min_order_qty", 0), ("unit_price", Decimal("-1")), ("lead_time_days", 0),
])
def test_invalid_product_values_rejected(db, field, value):
    with pytest.raises(IntegrityError):
        make_product(db, **{field: value})


def test_effective_lead_time_falls_back_to_supplier(db):
    product = make_product(db)
    assert product.effective_lead_time_days == 5
    product.lead_time_days = 9
    assert product.effective_lead_time_days == 9


def test_negative_stock_rejected(db):
    product = make_product(db)
    db.add(InventoryBalance(product_id=product.id, on_hand=-1))
    with pytest.raises(IntegrityError):
        db.flush()


def test_zero_quantity_transaction_rejected(db):
    product = make_product(db)
    db.add(InventoryTransaction(product_id=product.id, txn_type=TransactionType.ADJUSTMENT,
                                quantity=0, balance_after=5, reason="no-op"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_status_check_constraint_exists_in_database(db):
    # Bypass the ORM: the CHECK constraint itself must reject an unknown status.
    product = make_product(db)
    db.execute(text("INSERT INTO purchase_orders (po_number, supplier_id, status) VALUES ('PO-1', :s, 'draft')"),
               {"s": product.supplier_id})
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO purchase_orders (po_number, supplier_id, status) VALUES ('PO-2', :s, 'shipped')"),
                   {"s": product.supplier_id})


def test_orm_rejects_unknown_enum_value(db):
    product = make_product(db)
    db.add(InventoryTransaction(product_id=product.id, txn_type="teleport", quantity=1, balance_after=1))
    with pytest.raises(StatementError):
        db.flush()


def test_received_cannot_exceed_ordered(db):
    product = make_product(db)
    po = PurchaseOrder(po_number="PO-0001", supplier_id=product.supplier_id)
    po.items.append(PurchaseOrderItem(product_id=product.id, quantity_ordered=12, quantity_received=13))
    db.add(po)
    with pytest.raises(IntegrityError):
        db.flush()


def test_purchase_order_defaults_and_cascade(db):
    product = make_product(db)
    po = PurchaseOrder(po_number="PO-0002", supplier_id=product.supplier_id)
    po.items.append(PurchaseOrderItem(product_id=product.id, quantity_ordered=12))
    db.add(po)
    db.flush()
    assert po.status == PurchaseOrderStatus.DRAFT
    assert po.items[0].quantity_received == 0
    db.delete(po)
    db.flush()
    assert db.scalar(select(PurchaseOrderItem)) is None


def test_one_product_once_per_purchase_order(db):
    product = make_product(db)
    po = PurchaseOrder(po_number="PO-0003", supplier_id=product.supplier_id)
    po.items += [PurchaseOrderItem(product_id=product.id, quantity_ordered=6),
                 PurchaseOrderItem(product_id=product.id, quantity_ordered=6)]
    db.add(po)
    with pytest.raises(IntegrityError):
        db.flush()


def test_daily_sales_needs_known_calendar_day(db):
    product = make_product(db)
    db.add(DailySales(product_id=product.id, sales_date=date(2016, 1, 1), units=3))
    with pytest.raises(IntegrityError):    # no calendar_days row for that date
        db.flush()
    db.rollback()
    product = make_product(db, sku="FOODS_3_002")
    db.add_all([CalendarDay(day=date(2016, 1, 1)),
                DailySales(product_id=product.id, sales_date=date(2016, 1, 1), units=3)])
    db.flush()


def test_stockout_probability_must_be_between_0_and_1(db):
    product = make_product(db)
    run = RecommendationRun(policy_settings={"service_level": 0.95})
    db.add(run)
    db.flush()
    db.add(ReorderRecommendation(
        recommendation_run_id=run.id, product_id=product.id, on_hand=Decimal(5), inventory_position=Decimal(5),
        lead_time_days=5, suggested_qty=0, stockout_probability=Decimal("1.5"),
        risk_category=RiskCategory.HEALTHY, explanation="test"))
    with pytest.raises(IntegrityError):
        db.flush()
