"""Add a user account to an existing shop from the command line.

The password is typed at a hidden prompt, so it never appears on screen,
in shell history or in any file. To create a NEW shop with its first admin,
use create_shop.py instead.

    .venv\\Scripts\\python.exe backend\\scripts\\create_user.py --shop 1 --email you@example.com --name "Your Name" --role admin
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.db.tenancy import use_shop  # noqa: E402
from app.models import Shop  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.schemas.auth import UserCreate  # noqa: E402
from app.services.users import create_user  # noqa: E402


def ask_user_data(email: str, name: str, role: UserRole) -> UserCreate | None:
    """Ask for the password at a hidden prompt (twice). None if the input is not valid."""
    password = getpass.getpass("Password (min 10 characters, hidden): ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.")
        return None
    try:
        return UserCreate(email=email, full_name=name, password=password, role=role)
    except ValidationError as exc:
        for err in exc.errors():
            print(f"Invalid {err['loc'][0]}: {err['msg']}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a user account to a shop.")
    parser.add_argument("--shop", type=int, required=True, help="shop id (create_shop.py prints it)")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.VIEWER.value)
    args = parser.parse_args()

    with Session(get_engine()) as db:
        shop = db.get(Shop, args.shop)
        if shop is None:
            print(f"No shop with id {args.shop}.")
            return 1
        data = ask_user_data(args.email, args.name, UserRole(args.role))
        if data is None:
            return 1
        use_shop(db, shop.id)
        try:
            user = create_user(db, data)
        except AppError as exc:
            print(exc.detail)
            return 1
        print(f"Created {user.role.value} account {user.email} (id {user.id}) in shop {shop.id}: {shop.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
