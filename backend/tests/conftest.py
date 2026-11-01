"""Shared fixtures. Tests use in-memory SQLite databases so they run without
PostgreSQL or Docker; the PostgreSQL schema is checked in test_postgres_schema.py."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers every table)
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db, session_factory_dependency
from app.main import create_app
from app.models import CalendarDay, Category, DailySales, InventoryBalance, Product, Supplier, User
from app.models.enums import UserRole

# Test-only credentials for the in-memory test database.
TEST_PASSWORD = "test-password-123"
TEST_USERS = {
    "admin": ("admin@test.local", UserRole.ADMIN, True),
    "manager": ("manager@test.local", UserRole.MANAGER, True),
    "viewer": ("viewer@test.local", UserRole.VIEWER, True),
    "inactive": ("inactive@test.local", UserRole.MANAGER, False),
}


def _sqlite_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):   # SQLite ignores FKs unless asked
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db() -> Iterator[Session]:
    engine = _sqlite_engine()
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed_api_data(s: Session) -> None:
    # Low iteration count keeps tests fast; verify_password reads it from the stored hash.
    for email, role, active in TEST_USERS.values():
        s.add(User(email=email, full_name=role.value.title(), role=role, is_active=active,
                   hashed_password=hash_password(TEST_PASSWORD, iterations=1_000)))
    foods, hobbies = Category(code="FOODS", name="Foods"), Category(code="HOBBIES", name="Hobbies")
    supplier = Supplier(code="SUP_A", name="Supplier A", lead_time_days=3, lead_time_sd_days=Decimal("0.5"))
    s.add_all([foods, hobbies, supplier])
    s.flush()
    for i, (sku, cat, price, stock, cls) in enumerate([
        ("FOODS_1_001", foods, "2.50", 10, "smooth"),
        ("FOODS_1_002", foods, "1.00", 0, "intermittent"),
        ("HOBBIES_1_001", hobbies, "9.99", 5, "lumpy"),
    ]):
        product = Product(sku=sku, name=f"Item {i}", category=cat, supplier=supplier, unit_price=Decimal(price),
                          unit_cost=Decimal("0.50"), demand_class=cls)
        s.add(product)
        s.flush()
        s.add(InventoryBalance(product_id=product.id, on_hand=stock))
    start = date(2016, 1, 1)
    s.add_all([CalendarDay(day=start + timedelta(days=d)) for d in range(100)])
    s.flush()
    s.add_all([DailySales(product_id=1, sales_date=start + timedelta(days=d), units=d % 3) for d in range(100)])
    s.commit()


@pytest.fixture
def api() -> Iterator[TestClient]:
    """A test client with NO login, on a fresh in-memory database."""
    engine = _sqlite_engine()
    make_session = sessionmaker(bind=engine, expire_on_commit=False)
    with make_session() as s:
        _seed_api_data(s)

    def override() -> Iterator[Session]:
        with make_session() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db] = override
    application.dependency_overrides[session_factory_dependency] = lambda: make_session   # background jobs
    application.state.make_session = make_session   # lets tests set up rows the API cannot create yet
    with TestClient(application) as test_client:
        yield test_client
    engine.dispose()


def login(client: TestClient, role: str) -> dict[str, str]:
    """Log in as one of TEST_USERS and return the Authorization header."""
    response = client.post("/api/v1/auth/login", data={"username": TEST_USERS[role][0], "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def client(api: TestClient) -> TestClient:
    """The same client, logged in as a manager (can read and change products)."""
    api.headers.update(login(api, "manager"))
    return api
