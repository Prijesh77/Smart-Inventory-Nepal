"""The Nepali festival calendar (ml/calendar/nepal_festivals.json) and the forecast features made from it."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

from app.services.bs_calendar import from_bs, parse_date, to_bs
from ml.calendar.festivals import DATA_FILE, DAYS_CAP, FESTIVAL_FEATURES, coverage, festival_features, festivals, previous, upcoming

RAW = json.loads(DATA_FILE.read_text(encoding="utf-8"))


def test_every_entry_is_consistent_with_the_bs_calendar():
    first, last = coverage()
    assert first == from_bs(2081, 1, 1) and last == from_bs(2084, 1, 1) - timedelta(days=1)
    for f in RAW["festivals"]:
        assert parse_date(f["main_bs"])[0].isoformat() == f["main"], f
        for part in ("start", "end"):
            if part in f:
                assert parse_date(f[f"{part}_bs"])[0].isoformat() == f[part], f
        assert first <= date.fromisoformat(f["main"]) <= last, f
        assert f["sources"], f"{f['key']} {f['bs_year']} has no source"


def test_each_year_has_each_festival_once_with_sensible_windows():
    keys = {"dashain", "tihar", "chhath", "teej", "shivaratri", "holi", "new_year", "maghe_sankranti"}
    for year in (2081, 2082, 2083):
        found = [f["key"] for f in RAW["festivals"] if f["bs_year"] == year]
        assert sorted(found) == sorted(keys), year
    for f in festivals():
        assert to_bs(f.main).year in (2081, 2082, 2083)
        if f.key == "dashain":
            assert 8 <= (f.main - f.start).days <= 10                 # Ghatasthapana to Vijaya Dashami
        if f.key == "tihar":
            assert 2 <= (f.end - f.main).days <= 4                    # Laxmi Puja to Bhai Tika
        if f.key == "new_year":
            assert to_bs(f.main).month == 1 and to_bs(f.main).day == 1
    # Only the two dates the sources disagree on are marked for checking.
    assert sorted((f["key"], f["bs_year"]) for f in RAW["festivals"] if f["check"]) == [("holi", 2083), ("shivaratri", 2083)]


def test_features_around_tihar_2083():
    laxmi_puja = date(2026, 11, 8)
    rows = festival_features([laxmi_puja - timedelta(days=12), laxmi_puja - timedelta(days=5), laxmi_puja,
                              laxmi_puja + timedelta(days=3)])
    assert list(rows.columns) == FESTIVAL_FEATURES
    assert rows["days_to_tihar"].tolist() == [12, 5, 0, DAYS_CAP]          # after Tihar: next one is too far
    assert rows["in_tihar"].tolist() == [0, 1, 1, 1]                       # window: 10 days before to Bhai Tika
    assert rows["days_to_dashain"].iloc[2] == DAYS_CAP
    # Dashain 2083 (Vijaya Dashami 21 Oct) has a window up to 5 days after: in on 26 Oct, out on 27 Oct.
    edge = festival_features([date(2026, 10, 26), date(2026, 10, 27)])
    assert edge["in_dashain"].tolist() == [1, 0]


def test_unknown_years_are_missing_not_zero():
    first, last = coverage()
    rows = festival_features([first - timedelta(days=1), last + timedelta(days=1), last - timedelta(days=5)])
    assert all(math.isnan(v) for v in rows.iloc[0]) and all(math.isnan(v) for v in rows.iloc[1])
    assert math.isnan(rows["days_to_tihar"].iloc[2])                       # next Tihar's date is not known yet


def test_upcoming_and_last_years_festival():
    soon = upcoming(date(2026, 11, 1), within_days=14)
    assert [f.key for f in soon] == ["tihar", "chhath"]
    last_tihar = previous(soon[0])
    assert last_tihar.main == date(2025, 10, 20) and previous(last_tihar).main == date(2024, 10, 31)


def test_festival_calendar_endpoint(client, api):   # client = api, logged in as a manager
    body = client.get("/api/v1/festivals").json()
    assert len(body["festivals"]) == len(RAW["festivals"]) and body["covers"]["from"] == "2024-04-13"
    tihar = next(f for f in body["festivals"] if f["key"] == "tihar" and f["bs_year"] == 2083)
    assert tihar["main"] == "2026-11-08" and tihar["main_bs"] == "2083-07-22" and tihar["sources"]
    assert api.get("/api/v1/festivals", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
