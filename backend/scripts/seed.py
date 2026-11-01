"""Add the synthetic demo shop to the database (as its own shop), then train its forecast model.

What is loaded (ALL SYNTHETIC, see backend/app/services/demo_shop.py):
  "Demo Kirana Pasal": 6 categories, 4 suppliers, 43 everyday products with
  prices in rupees, about 18 months of generated daily sales ending yesterday,
  opening stock (recorded as 'initial' inventory transactions), festival days
  (approximate Dashain/Tihar dates) and the default reorder settings.
No M5 or other real data is used.

Run from the project root (after `alembic upgrade head`):
    .venv\\Scripts\\python.exe backend\\scripts\\seed.py            # refuses if data exists
    .venv\\Scripts\\python.exe backend\\scripts\\seed.py --reset    # wipes ALL app data first
Options: --end 2026-10-31 (last sales day, default yesterday), --no-train.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.db.tenancy import all_shops  # noqa: E402
from app.models import Product  # noqa: E402
from app.services import demo_shop  # noqa: E402


def reset(session: Session) -> None:
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the synthetic demo shop.")
    parser.add_argument("--reset", action="store_true", help="delete ALL existing app data first")
    parser.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1),
                        help="last day of generated sales (YYYY-MM-DD, default yesterday)")
    parser.add_argument("--no-train", action="store_true", help="skip training the Random Forest")
    args = parser.parse_args()

    engine = get_engine()
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    start = time.perf_counter()
    data = demo_shop.generate(args.end)
    with Session(engine) as session, session.begin():   # one transaction: all or nothing
        with all_shops(session):
            existing = session.scalar(select(func.count()).select_from(Product))
        if existing and not args.reset:
            raise SystemExit(f"Database already has {existing} products. Use --reset to wipe and reload.")
        if args.reset:
            reset(session)
            print("Existing data removed.")
        counts = demo_shop.load(session, data)
    print(f"{demo_shop.DEMO_SHOP_NAME}: sales {data.start} .. {data.end}")
    for key, value in counts.items():
        print(f"  {key:22s} {value}")
    print(f"Loaded in {time.perf_counter() - start:.0f} s")

    if not args.no_train:
        from train_model import train_and_report
        train_and_report(engine, [counts["shop_id"]])


if __name__ == "__main__":
    main()
