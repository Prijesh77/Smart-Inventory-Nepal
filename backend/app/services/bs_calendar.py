"""Bikram Sambat (BS) dates and the Nepali fiscal year.

The database and API always store Gregorian (AD) dates; BS is for reading
and typing dates the way Nepali shops do. Conversion uses the nepali-datetime
package (MIT), which holds the official month-length tables for BS 1975-2100.
The frontend converts with the same month table, exported to
frontend/src/lib/bs-calendar.json (a test checks the file is up to date), so
the browser and the server never disagree. BS years beyond the officially
published calendar are estimates (converters differ by a day there): regenerate
the table with backend/scripts/export_bs_calendar.py when it is updated.

Fiscal year: 1 Shrawan to the last day of Asar, e.g. FY 2083/84 runs from
1 Shrawan 2083 (17 July 2026) to the end of Asar 2084.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import nepali_datetime as nd

MONTHS = ["Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Asoj",
          "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"]
SHRAWAN = 4
FIRST_BS_YEAR, LAST_BS_YEAR = nd.MINYEAR, nd.MAXYEAR
# A date written with a year from 2051 up is BS: shop data in AD is decades away from 2051,
# and BS 2051 was AD 1994, before any data the app could hold.
BS_YEAR_FROM = 2051
_DATE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")


@dataclass(frozen=True)
class BsDate:
    year: int
    month: int          # 1 = Baisakh ... 12 = Chaitra
    day: int

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}-{self.day:02d}"

    @property
    def label(self) -> str:
        return f"{self.day} {MONTHS[self.month - 1]} {self.year}"


def to_bs(day: date) -> BsDate:
    d = nd.date.from_datetime_date(day)
    return BsDate(d.year, d.month, d.day)


def from_bs(year: int, month: int, day: int) -> date:
    """AD date for a BS date; ValueError if that BS date does not exist (e.g. Baisakh 32 in a 31-day year)."""
    if not FIRST_BS_YEAR <= year <= LAST_BS_YEAR:
        raise ValueError(f"BS year {year} is outside {FIRST_BS_YEAR}-{LAST_BS_YEAR}")
    try:
        return nd.date(year, month, day).to_datetime_date()
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{year}-{month:02d}-{day:02d} is not a BS date") from exc


def parse_date(text: str) -> tuple[date, bool]:
    """'2026-11-01' (AD) or '2083-07-15' (BS, any year from 2051) -> (AD date, was_bs).

    Separators '-', '/' or '.' are accepted. ValueError if it is not a real date in its calendar.
    """
    match = _DATE.match(text.strip())
    if not match:
        raise ValueError(f"'{text}' is not YYYY-MM-DD")
    year, month, day = (int(g) for g in match.groups())
    if year >= BS_YEAR_FROM:
        return from_bs(year, month, day), True
    return date(year, month, day), False


@dataclass(frozen=True)
class FiscalYear:
    start_year: int     # BS year in which the fiscal year starts (on 1 Shrawan)
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.start_year}/{(self.start_year + 1) % 100:02d}"


def fiscal_year(day: date) -> FiscalYear:
    """The Nepali fiscal year (1 Shrawan to the end of Asar) containing `day`."""
    bs = to_bs(day)
    start_year = bs.year if bs.month >= SHRAWAN else bs.year - 1
    start = from_bs(start_year, SHRAWAN, 1)
    end = date.fromordinal(from_bs(start_year + 1, SHRAWAN, 1).toordinal() - 1)
    return FiscalYear(start_year, start, end)


# BS 2000 - 2090 = AD 1943 - 2034. Later years in the converter are rough estimates (it gives 2096 only
# 364 days), so dates after the table are shown in AD rather than guessed.
TABLE_FIRST_YEAR, TABLE_LAST_YEAR = 2000, 2090


def month_lengths(year: int) -> list[int]:
    starts = [from_bs(year, m, 1) for m in range(1, 13)] + [from_bs(year + 1, 1, 1)]
    return [(b - a).days for a, b in zip(starts, starts[1:])]


def calendar_table(first_year: int = TABLE_FIRST_YEAR, last_year: int = TABLE_LAST_YEAR) -> dict[str, dict]:
    """Per BS year: the AD date of 1 Baisakh and the 12 month lengths. The frontend converts dates with
    this exact table (frontend/src/lib/bs-calendar.json), so the browser and the server always agree."""
    return {str(y): {"start": from_bs(y, 1, 1).isoformat(), "months": month_lengths(y)}
            for y in range(first_year, last_year + 1)}


def write_frontend_table(path) -> None:
    import json
    data = {"note": "Generated from nepali-datetime by backend/scripts/export_bs_calendar.py. Do not edit by hand. "
                    "Years after the officially published calendar are estimates; regenerate when it is updated.",
            "years": calendar_table()}
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
