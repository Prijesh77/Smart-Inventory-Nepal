"""Prepare the end-to-end test database: migrate, load the synthetic demo shop, create test accounts.

The demo shop (shop 1) gets an admin, a manager and a viewer. A second, small shop
with its own admin and one product is added so the tests can check, in a real
browser, that one shop never sees another's data.

    ..\\.venv\\Scripts\\python.exe ..\\backend\\scripts\\e2e_setup.py     (run by `npm run e2e`)

Test accounts get NEW random passwords on every run. They are written only to
frontend/e2e/.credentials.json (git-ignored) for Playwright to read; nothing
secret is printed.
"""

from __future__ import annotations

import json
import secrets
from decimal import Decimal
import subprocess
import sys

from e2e_common import CREDENTIALS_FILE, ROOT, use_e2e_database


def main() -> int:
    database = use_e2e_database()

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import OperationalError

    from app.core.config import get_settings

    try:
        with create_engine(get_settings().database_url, connect_args={"connect_timeout": 5}).connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        print(f"Cannot connect to the '{database}' database: {str(exc.orig).strip().splitlines()[0]}")
        user = make_url(get_settings().database_url).username
        print(f"Create it once in pgAdmin (as postgres):  CREATE DATABASE {database} OWNER {user};")
        return 1

    env = {**__import__("os").environ}
    steps = [
        ("migrate", [sys.executable, "-m", "alembic", "upgrade", "head"], ROOT / "backend"),
        ("seed", [sys.executable, str(ROOT / "backend" / "scripts" / "seed.py"), "--reset"], ROOT),
    ]
    for name, cmd, cwd in steps:
        result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
        if result.returncode:
            print(f"{name} failed:\n{result.stdout[-1500:]}\n{result.stderr[-1500:]}")
            return 1

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.session import get_engine
    from app.db.tenancy import all_shops, use_shop
    from app.models import Category, InventoryBalance, Product, Shop
    from app.models.enums import UserRole
    from app.schemas.auth import UserCreate
    from app.services.shops import create_shop
    from app.services.users import create_user

    accounts = {}
    with Session(get_engine()) as db:
        with all_shops(db):                              # the demo shop that seed.py just created
            use_shop(db, db.scalar(select(Shop.id).where(Shop.is_demo.is_(True)).order_by(Shop.id)))
        for role in (UserRole.ADMIN, UserRole.MANAGER, UserRole.VIEWER):
            password = secrets.token_urlsafe(18)
            email = f"e2e-{role.value}@test.local"
            create_user(db, UserCreate(email=email, full_name=f"E2E {role.value.title()}", password=password, role=role))
            accounts[role.value] = {"email": email, "password": password}

        # A second shop: its own admin and one product that the demo shop must never show.
        other = create_shop(db, "E2E Second Shop")
        category = Category(code="OTHER", name="Other shop's goods")
        db.add(category)
        db.flush()
        product = Product(sku="ONLY-IN-SHOP-B", name="Item only the second shop has", category=category,
                          unit_price=Decimal("99.00"))
        db.add(product)
        db.flush()
        db.add(InventoryBalance(product_id=product.id, on_hand=5, backorders=0))
        password = secrets.token_urlsafe(18)
        create_user(db, UserCreate(email="e2e-other-shop@test.local", full_name="E2E Other Shop Admin",
                                   password=password, role=UserRole.ADMIN))           # commits the shop too
        accounts["other_shop"] = {"email": "e2e-other-shop@test.local", "password": password, "shop": other.name}
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
    print(f"E2E database '{database}' ready: migrated, demo shop + second shop, {len(accounts)} test accounts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
