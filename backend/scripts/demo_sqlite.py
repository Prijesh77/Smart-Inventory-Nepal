"""Try the app on the synthetic demo shop WITHOUT PostgreSQL, using a local SQLite file.

    .venv\\Scripts\\python.exe backend\\scripts\\demo_sqlite.py setup   # build data/demo/demo.db, train, make a demo admin
    .venv\\Scripts\\python.exe backend\\scripts\\demo_sqlite.py serve   # API on http://127.0.0.1:8000 using that file (--port 8001 if 8000 is busy)
Then start the frontend (cd frontend; npm run dev) and log in with one of the two demo shops' admin accounts in
data/demo/credentials.json (git-ignored; new random passwords on every setup).

For development and demos only: the real app uses PostgreSQL with Alembic migrations.
This never touches the database in .env.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "data" / "demo"
DB_FILE = DEMO_DIR / "demo.db"
CREDENTIALS_FILE = DEMO_DIR / "credentials.json"

MODEL_DIR = DEMO_DIR / "models"

os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"   # overrides .env for this process only
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]


def use_demo_model_folder() -> None:
    """Keep this demo's trained models apart from the main database's: both have a shop 1."""
    import app.services.forecast_engine as engine
    engine.MODEL_DIR = MODEL_DIR


def setup() -> None:
    use_demo_model_folder()
    from sqlalchemy.orm import Session

    import app.models  # noqa: F401  (registers every table)
    from app.db.base import Base
    from app.db.session import get_engine
    from app.models.enums import UserRole
    from app.schemas.auth import UserCreate
    from app.services import demo_shop
    from app.services.users import create_user
    from train_model import train_and_report

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    DB_FILE.unlink(missing_ok=True)
    engine = get_engine()
    Base.metadata.create_all(engine)
    end = date.today() - timedelta(days=1)
    # Two separate demo shops, so you can log in to each and see that their data never mixes.
    shops = [(demo_shop.DEMO_SHOP_NAME, demo_shop.DEMO_SEED, "demo-admin@test.local"),
             ("Second Demo Pasal (synthetic data)", demo_shop.DEMO_SEED + 1, "demo2-admin@test.local")]
    accounts = []
    for name, seed, email in shops:
        data = demo_shop.generate(end, seed=seed)
        password = secrets.token_urlsafe(18)
        with Session(engine) as session:
            counts = demo_shop.load(session, data, name=name)
            create_user(session, UserCreate(email=email, full_name=f"Admin, {name}", password=password,
                                            role=UserRole.ADMIN))           # commits the shop and its admin
        print(f"Shop {counts['shop_id']} {name}: sales {data.start} .. {data.end}, {counts['products']} products")
        accounts.append({"shop": name, "email": email, "password": password})
    train_and_report(engine)

    CREDENTIALS_FILE.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
    print(f"Demo admin accounts written to {CREDENTIALS_FILE.relative_to(ROOT)} (passwords not printed).")


def serve(port: int = 8000) -> None:
    import uvicorn

    use_demo_model_folder()

    if not DB_FILE.exists():
        raise SystemExit("Run 'demo_sqlite.py setup' first.")
    os.chdir(ROOT / "backend")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    if sys.argv[1:2] == ["setup"] and len(sys.argv) == 2:
        setup()
    elif sys.argv[1:2] == ["serve"] and len(sys.argv) in (2, 4) and sys.argv[2:3] in ([], ["--port"]):
        serve(int(sys.argv[3]) if len(sys.argv) == 4 else 8000)
    else:
        raise SystemExit(__doc__)
