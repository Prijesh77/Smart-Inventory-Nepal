"""Integration tests against the real PostgreSQL database in DATABASE_URL.

Every test runs inside a transaction that is rolled back, so the database is
left unchanged. Skipped automatically when the database is not reachable
(e.g. on a machine without PostgreSQL). Run only these with:  pytest -m postgres
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    AppSetting, Category, InventoryBalance, Product, PurchaseOrder, PurchaseOrderItem, Supplier,
)

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def pg_engine():
    try:
        from app.core.config import get_settings
        engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            if conn.dialect.name != "postgresql":
                pytest.skip("DATABASE_URL is not PostgreSQL")
            if not inspect(conn).has_table("products"):
                pytest.skip("Schema not migrated; run: alembic upgrade head")
    except pytest.skip.Exception:
        raise
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable: {type(exc).__name__}")
    yield engine
    engine.dispose()


@pytest.fixture
def pg(pg_engine) -> Iterator[Session]:
    """A session whose work is always rolled back at the end of the test."""
    with pg_engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


def _product(pg: Session, sku: str = "TEST_SKU_1", **overrides) -> Product:
    category = Category(code=f"CAT_{sku}", name="Test")
    supplier = Supplier(code=f"SUP_{sku}", name="Test supplier", lead_time_days=5)
    product = Product(**{"sku": sku, "name": "Test", "category": category, "supplier": supplier,
                         "unit_price": Decimal("1.00"), **overrides})
    pg.add(product)
    pg.flush()
    return product


def test_migrated_schema_matches_models(pg_engine):
    with pg_engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
    assert set(Base.metadata.tables) <= tables


def test_duplicate_sku_rejected(pg):
    _product(pg, "TEST_DUP")
    with pytest.raises(IntegrityError):
        pg.add(Product(sku="TEST_DUP", name="Again", category_id=pg.scalar(select(Category.id).limit(1)),
                       unit_price=Decimal("1.00")))
        pg.flush()


def test_negative_stock_rejected(pg):
    product = _product(pg)
    pg.add(InventoryBalance(product_id=product.id, on_hand=-5))
    with pytest.raises(IntegrityError):
        pg.flush()


def test_unknown_status_rejected_by_database(pg):
    product = _product(pg)
    with pytest.raises(IntegrityError):
        pg.execute(text("INSERT INTO purchase_orders (po_number, supplier_id, status) "
                        "VALUES ('TEST-PO', :s, 'shipped')"), {"s": product.supplier_id})


def test_received_cannot_exceed_ordered(pg):
    product = _product(pg)
    po = PurchaseOrder(po_number="TEST-PO-1", supplier_id=product.supplier_id)
    po.items.append(PurchaseOrderItem(product_id=product.id, quantity_ordered=6, quantity_received=7))
    pg.add(po)
    with pytest.raises(IntegrityError):
        pg.flush()


def test_purchase_order_lifecycle_with_row_locks(pg):
    """Draft -> submit -> receive on real PostgreSQL (SELECT ... FOR UPDATE is only exercised here)."""
    from app.models import InventoryTransaction, User
    from app.models.enums import PurchaseOrderStatus, TransactionType, UserRole
    from app.services import inventory, purchasing

    product = _product(pg, "TEST_PO_SKU", unit_cost=Decimal("2.00"))
    pg.add(InventoryBalance(product_id=product.id, on_hand=3))
    user = User(email="pg-test@test.local", full_name="PG Test", hashed_password="x", role=UserRole.MANAGER)
    pg.add(user)
    pg.flush()

    po = purchasing.create_draft(pg, supplier_id=product.supplier_id, lines=[{"product_id": product.id, "quantity": 6}],
                                 notes=None, expected_date=None, user=user)
    po = purchasing.submit(pg, po.id)
    assert inventory.stock_for_product(pg, product.id)["on_order"] == 6
    po = purchasing.receive(pg, po.id, [{"item_id": po.items[0].id, "quantity": 6}], user)
    assert po.status == PurchaseOrderStatus.RECEIVED
    assert pg.get(InventoryBalance, product.id).on_hand == 9
    receipt = pg.scalar(select(InventoryTransaction).where(InventoryTransaction.purchase_order_id == po.id))
    assert receipt.txn_type == TransactionType.RECEIPT and receipt.balance_after == 9


def test_money_is_exact_and_json_round_trips(pg):
    product = _product(pg, unit_price=Decimal("0.10") + Decimal("0.20"))
    pg.add(AppSetting(key="test_policy", value={"service_level": 0.95, "horizons": [7, 14, 28]}))
    pg.flush()
    pg.expire_all()
    assert pg.get(Product, product.id).unit_price == Decimal("0.30")      # no float drift
    assert pg.get(AppSetting, "test_policy").value["horizons"] == [7, 14, 28]
    column_type = pg.execute(text(
        "SELECT data_type FROM information_schema.columns WHERE table_name='app_settings' AND column_name='value'"
    )).scalar()
    assert column_type == "jsonb"
