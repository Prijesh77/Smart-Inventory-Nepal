"""Smart Inventory API: FastAPI application, database models and services."""

import os
import sys
from pathlib import Path

# SQLAlchemy's optional compiled speed-ups are blocked by Windows Smart App Control on
# this machine (it then falls back to plain Python anyway). Skip loading them so
# Windows does not show a warning every time the app starts.
os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")

# The API reuses the research code in <project root>/ml (forecasting and the
# reorder engine), so the same tested formulas run in experiments and the app.
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.append(_PROJECT_ROOT)
