"""Create a user account from the command line (needed for the very first admin).

The password is typed at a hidden prompt, so it never appears on screen,
in shell history or in any file.

    .venv\\Scripts\\python.exe backend\\scripts\\create_user.py --email you@example.com --name "Your Name" --role admin
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
from app.models.enums import UserRole  # noqa: E402
from app.schemas.auth import UserCreate  # noqa: E402
from app.services.users import create_user  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a user account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.VIEWER.value)
    args = parser.parse_args()

    password = getpass.getpass("Password (min 10 characters, hidden): ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.")
        return 1
    try:
        data = UserCreate(email=args.email, full_name=args.name, password=password, role=UserRole(args.role))
    except ValidationError as exc:
        for err in exc.errors():
            print(f"Invalid {err['loc'][0]}: {err['msg']}")
        return 1
    with Session(get_engine()) as db:
        try:
            user = create_user(db, data)
        except AppError as exc:
            print(exc.detail)
            return 1
    print(f"Created {user.role.value} account {user.email} (id {user.id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
