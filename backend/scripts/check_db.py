"""Check that the database in DATABASE_URL (.env) is reachable. Never prints the password.

    cd backend
    python scripts/check_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    url = make_url(get_settings().database_url)
    print(f"Target: user={url.username} host={url.host} port={url.port} database={url.database}")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            version = conn.execute(text("select version()")).scalar().split(",")[0]
            user = conn.execute(text("select current_user")).scalar()
            tables = conn.execute(text(
                "select count(*) from information_schema.tables where table_schema = 'public'")).scalar()
    except Exception as exc:   # report any failure in one readable line
        print(f"FAILED: {type(exc).__name__}: {str(exc).strip().splitlines()[0][:300]}")
        return 1
    print(f"OK: {version}; connected as {user}; {tables} tables in schema 'public'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
