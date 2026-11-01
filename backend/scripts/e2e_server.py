"""Run the API against the end-to-end database (used by Playwright's webServer).

    ..\\.venv\\Scripts\\python.exe ..\\backend\\scripts\\e2e_server.py --port 8001
"""

from __future__ import annotations

import argparse
import os

from e2e_common import ROOT, use_e2e_database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    use_e2e_database()
    os.chdir(ROOT / "backend")

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
