"""Shared helpers for the browser end-to-end tests.

The tests run against a SEPARATE database: the main database's name plus
"_e2e" (same server, user and password as DATABASE_URL in .env), e.g.
smart_inventory_nepal_e2e. They never touch the main database: every entry point
checks the name first. Trained models go to data/e2e/models, not models/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

MODEL_DIR = ROOT / "data" / "e2e" / "models"
CREDENTIALS_FILE = ROOT / "frontend" / "e2e" / ".credentials.json"


def use_e2e_database() -> str:
    """Point DATABASE_URL at the e2e database for this process. Returns the database name."""
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

    main_url = make_url(get_settings().database_url)
    e2e_url = main_url.set(database=f"{main_url.database}_e2e")
    if not e2e_url.database.endswith("_e2e") or e2e_url.database == main_url.database:
        raise SystemExit("Refusing to run: the end-to-end database must be separate and end in '_e2e'")
    os.environ["DATABASE_URL"] = e2e_url.render_as_string(hide_password=False)
    os.environ["MODEL_DIR"] = str(MODEL_DIR)
    get_settings.cache_clear()
    return e2e_url.database
