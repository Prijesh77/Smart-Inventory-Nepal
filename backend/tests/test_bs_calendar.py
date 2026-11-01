"""Bikram Sambat conversion and the Nepali fiscal year (backend/app/services/bs_calendar.py)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.core.config import PROJECT_ROOT
from app.services.bs_calendar import BsDate, calendar_table, fiscal_year, from_bs, parse_date, to_bs

FIXTURE = PROJECT_ROOT / "frontend" / "src" / "lib" / "bs-calendar.json"


@pytest.mark.parametrize("ad, bs", [
    (date(2026, 4, 14), BsDate(2083, 1, 1)),      # Nepali New Year 2083
    (date(2026, 11, 1), BsDate(2083, 7, 15)),     # 15 Kartik 2083
    (date(2026, 7, 17), BsDate(2083, 4, 1)),      # 1 Shrawan 2083: fiscal year starts
    (date(2025, 4, 14), BsDate(2082, 1, 1)),
])
def test_known_dates(ad, bs):
    assert to_bs(ad) == bs
    assert from_bs(bs.year, bs.month, bs.day) == ad


def test_every_day_converts_there_and_back():
    day = date(2013, 4, 14)                         # BS 2070 to 2095
    while day < date(2039, 4, 14):
        bs = to_bs(day)
        assert from_bs(bs.year, bs.month, bs.day) == day
        day += timedelta(days=1)


def test_parse_reads_ad_and_bs_by_the_year():
    assert parse_date("2026-11-01") == (date(2026, 11, 1), False)
    assert parse_date("2083-07-15") == (date(2026, 11, 1), True)
    assert parse_date("2083/7/15") == (date(2026, 11, 1), True)
    assert parse_date(" 2083.07.15 ") == (date(2026, 11, 1), True)
    for bad in ["2083-07-31", "2083-13-01", "2026-02-30", "15/07/2083", "yesterday"]:   # Kartik 2083 has 30 days
        with pytest.raises(ValueError):
            parse_date(bad)


def test_fiscal_year_runs_from_shrawan_to_asar():
    fy = fiscal_year(date(2026, 11, 1))
    assert fy.label == "2083/84" and fy.start == date(2026, 7, 17)
    assert to_bs(fy.end).month == 3 and to_bs(fy.end).year == 2084            # last day of Asar 2084
    assert fiscal_year(fy.start - timedelta(days=1)).label == "2082/83"       # the day before 1 Shrawan
    assert fiscal_year(fy.end).label == "2083/84" and fiscal_year(fy.end + timedelta(days=1)).label == "2084/85"


def test_the_frontend_table_is_up_to_date():
    """The browser converts with frontend/src/lib/bs-calendar.json. It must be exactly this converter's table,
    so both sides always show the same BS dates. Fix: run backend/scripts/export_bs_calendar.py."""
    years = json.loads(FIXTURE.read_text(encoding="utf-8"))["years"]
    assert years == calendar_table()
    assert all(29 <= n <= 32 for y in years.values() for n in y["months"])
    assert all(365 <= sum(y["months"]) <= 366 for y in years.values())
