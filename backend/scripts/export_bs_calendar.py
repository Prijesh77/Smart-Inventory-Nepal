"""Write the BS month table the frontend uses (frontend/src/lib/bs-calendar.json) from the backend's converter.

    .venv\\Scripts\\python.exe backend\\scripts\\export_bs_calendar.py
Run it after upgrading nepali-datetime (e.g. when the official calendar for new years is published).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.services.bs_calendar import write_frontend_table  # noqa: E402

if __name__ == "__main__":
    target = ROOT / "frontend" / "src" / "lib" / "bs-calendar.json"
    write_frontend_table(target)
    print(f"Wrote {target.relative_to(ROOT)}")
