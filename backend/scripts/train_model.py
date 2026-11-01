"""Train each shop's Random Forest on that shop's own sales (models/shop_<id>_random_forest.joblib).

Run again after importing new sales. From the project root:
    .venv\\Scripts\\python.exe backend\\scripts\\train_model.py            # every shop
    .venv\\Scripts\\python.exe backend\\scripts\\train_model.py --shop 2   # one shop
Shops with too little history are skipped (they use the 28-day moving average).
Takes under a minute for a shop with a few hundred products.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from sqlalchemy.orm import Session  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.db.tenancy import use_shop  # noqa: E402
from app.services.forecast_engine import ForecastUnavailable  # noqa: E402
from app.services.model_training import train_shop_model  # noqa: E402
from app.services.shops import list_shops  # noqa: E402


def train_and_report(engine, shop_ids: list[int] | None = None) -> None:
    with Session(engine) as session:
        shops = [s for s in list_shops(session) if shop_ids is None or s.id in shop_ids]
    for shop in shops:
        start = time.perf_counter()
        with Session(engine) as session:
            use_shop(session, shop.id)
            try:
                summary = train_shop_model(session)
            except (ForecastUnavailable, AppError) as exc:
                print(f"Shop {shop.id} ({shop.name}): not trained. {exc}")
                continue
        print(f"Shop {shop.id} ({shop.name}): Random Forest trained on its own sales")
        for key, value in summary.items():
            print(f"  {key:26s} {value}")
        print(f"  trained in {time.perf_counter() - start:.0f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train each shop's forecast model.")
    parser.add_argument("--shop", type=int, action="append", help="only this shop id (repeatable)")
    train_and_report(get_engine(), parser.parse_args().shop)


if __name__ == "__main__":
    main()
