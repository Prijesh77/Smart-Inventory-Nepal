"""Incomplete sales records: days with nothing recorded, days only partly entered, and how forecasts cope.

Seeded data (conftest.py): product 1 sells d % 3 units every day 2016-01-01 .. 2016-04-09; products 2 and 3 never
sell. The `planning` fixture adds 100 earlier days for product 1 so the models have enough history.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete

from app.models import DailySales
from app.services.forecast_engine import fill_unrecorded_zeros
from tests.test_api_planning import planning  # noqa: F401  (fixture)

LAST = date(2016, 4, 9)


def test_complete_records_have_no_warnings(client):
    body = client.get("/api/v1/sales/coverage").json()
    assert body["window_end"] == "2016-04-09" and body["window_start"] == "2016-03-13"
    assert body["recorded_days"] == 28 and body["missing_days"] == []
    assert body["partial_days"] == []                 # products 2 and 3 never sold, so they are not expected


def test_days_with_nothing_recorded_are_listed(client, api):
    gap = [LAST - timedelta(days=k) for k in range(3, 13)]           # 10 days, ending 3 days before the last day
    with api.app.state.make_session() as s:
        s.execute(delete(DailySales).where(DailySales.sales_date.in_(gap)))
        s.commit()
    body = client.get("/api/v1/sales/coverage").json()
    assert body["recorded_days"] == 18 and body["missing_days"] == sorted(str(d) for d in gap)


def test_auto_uses_the_moving_average_when_most_recent_days_are_missing(planning, api, empty_model_folder):  # noqa: F811
    from ml.features.build import FEATURES
    empty_model_folder.mkdir()
    (empty_model_folder / "shop_1_random_forest.joblib").write_bytes(b"trained")
    (empty_model_folder / "shop_1_random_forest.json").write_text(json.dumps({"features": FEATURES}))
    run = planning.post("/api/v1/forecasts/runs", json={"horizon_days": 7}).json()
    assert run["model_name"] == "random_forest_v1"                  # complete records: the forest

    with api.app.state.make_session() as s:                          # only 10 of the last 28 days recorded
        s.execute(delete(DailySales).where(DailySales.sales_date.between(LAST - timedelta(days=27), LAST - timedelta(days=10))))
        s.commit()
    run = planning.post("/api/v1/forecasts/runs", json={"horizon_days": 7}).json()
    assert run["model_name"] == "moving_avg_28" and "only 10 of the 28 days" in run["params"]["model_choice"]


def test_products_missing_on_a_recorded_day_count_as_zero():
    d = [date(2026, 1, k) for k in (1, 2, 3, 5)]                     # nothing at all recorded on 4 January
    daily = pd.DataFrame({
        "product_id": [1, 1, 2, 1], "item_id": ["A", "A", "B", "A"], "dept_id": "X", "cat_id": "C",
        "sales_date": [d[0], d[1], d[1], d[3]], "sales": [2.0, 1.0, 5.0, 3.0], "sell_price": 10.0,
        "is_available": True, "list_price": [10.0, 10.0, 20.0, 10.0]})
    # day 3 has no rows at all, so it is not a recorded day; product B starts selling on 2 January
    out = fill_unrecorded_zeros(daily[daily["sales_date"] != d[2]])
    b = out[out["item_id"] == "B"].set_index("sales_date")["sales"]
    assert b.to_dict() == {d[1]: 5.0, d[3]: 0.0}                     # not before its first sale; 0 on 5 January
    assert date(2026, 1, 4) not in set(out["sales_date"])             # an unrecorded day stays unknown
    assert np.isclose(out.loc[(out["item_id"] == "B") & (out["sales_date"] == d[3]), "sell_price"], 20.0).all()


def test_days_where_a_selling_product_has_no_entry_are_partial(client, api):
    with api.app.state.make_session() as s:                          # product 3 starts selling 5 days before the end
        s.add(DailySales(product_id=3, sales_date=LAST - timedelta(days=5), units=1))
        s.commit()
    partial = client.get("/api/v1/sales/coverage").json()["partial_days"]
    assert [p["date"] for p in partial] == [str(LAST - timedelta(days=k)) for k in range(4, -1, -1)]
    assert partial[0]["products_recorded"] == 1 and partial[0]["products_expected"] == 2
