"""Create a new shop (a business that will use the app) and its first admin account.

Each shop's products, stock, sales, orders, forecasts and users are private to it.
The admin's password is typed at a hidden prompt; the admin can add more users
from Settings in the app.

    .venv\\Scripts\\python.exe backend\\scripts\\create_shop.py --name "Shrestha Kirana Pasal" --email owner@example.com --admin-name "Ram Shrestha"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from sqlalchemy.orm import Session  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.services.shops import create_shop  # noqa: E402
from app.services.users import create_user  # noqa: E402
from create_user import ask_user_data  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a shop and its first admin.")
    parser.add_argument("--name", required=True, help="the business name shown in the app")
    parser.add_argument("--email", required=True, help="the first admin's login email")
    parser.add_argument("--admin-name", required=True)
    args = parser.parse_args()

    data = ask_user_data(args.email, args.admin_name, UserRole.ADMIN)
    if data is None:
        return 1
    with Session(get_engine()) as db:
        try:
            shop = create_shop(db, args.name)
            user = create_user(db, data)              # commits the shop and the admin together
        except AppError as exc:
            db.rollback()
            print(exc.detail)
            return 1
        print(f"Created shop {shop.id}: {shop.name}, with admin {user.email}.")
    print("Next: log in, then import products, opening stock and sales (Settings & import).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
