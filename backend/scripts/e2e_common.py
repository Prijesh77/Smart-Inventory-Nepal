"""Shared helpers for the browser end-to-end tests.

The tests run against a SEPARATE database whose name ends in "_e2e" (same
server, user and password as DATABASE_URL in .env). They never touch the
main database: every entry point checks the name first.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

E2E_DATABASE = "inventory_e2e"
CREDENTIALS_FILE = ROOT / "frontend" / "e2e" / ".credentials.json"


def use_e2e_database() -> str:
    """Point DATABASE_URL at the e2e database for this process. Returns the database name."""
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

    main_url = make_url(get_settings().database_url)
    e2e_url = main_url.set(database=E2E_DATABASE)
    if not e2e_url.database.endswith("_e2e") or e2e_url.database == main_url.database:
        raise SystemExit("Refusing to run: the end-to-end database must be separate and end in '_e2e'")
    os.environ["DATABASE_URL"] = e2e_url.render_as_string(hide_password=False)
    get_settings.cache_clear()
    return e2e_url.database
