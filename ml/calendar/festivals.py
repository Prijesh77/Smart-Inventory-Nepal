"""Nepali festivals as forecast features (replaces the M5 data's US events and SNAP days).

The dates live in nepal_festivals.json (AD and BS, with sources). For every day the
forecast looks at, this module says how far the next Dashain and Tihar are, and
whether the day is in a festival's build-up window, when shops sell much more.

Days outside the years the file covers get NaN ("unknown"), not 0 ("no festival"):
a festival we have no date for must not teach the model that nothing happens then.
(scikit-learn's Random Forest accepts missing values.)
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DATA_FILE = Path(__file__).with_name("nepal_festivals.json")
MAJOR = ("dashain", "tihar")
DAYS_CAP = 45            # "more than 6 weeks away" is all the same to a shop
# Build-up window, in days, around the main day (or the festival's own start/end when it has one).
WINDOW_BEFORE = {"dashain": 7, "tihar": 10}         # Dashain: 7 days before Ghatasthapana; Tihar: before Laxmi Puja
WINDOW_AFTER = {"dashain": 5}                       # up to Kojagrat Purnima
OTHER_BEFORE = 3
FESTIVAL_FEATURES = ["days_to_dashain", "days_to_tihar", "in_dashain", "in_tihar", "in_other_festival"]


@dataclass(frozen=True)
class Festival:
    key: str
    name: str
    main_label: str
    main: date
    start: date | None
    end: date | None
    main_bs: str
    check: bool

    @property
    def window(self) -> tuple[date, date]:
        """First and last day of the build-up (when sales usually rise)."""
        first = (self.start or self.main) - timedelta(days=WINDOW_BEFORE.get(self.key, OTHER_BEFORE))
        last = (self.end or self.main) + timedelta(days=WINDOW_AFTER.get(self.key, 0))
        return first, last


@lru_cache
def _load(path: Path = DATA_FILE) -> tuple[tuple[Festival, ...], date, date]:
    data = json.loads(path.read_text(encoding="utf-8"))
    festivals = tuple(
        Festival(key=f["key"], name=f["name"], main_label=f["main_label"], main=date.fromisoformat(f["main"]),
                 start=date.fromisoformat(f["start"]) if f.get("start") else None,
                 end=date.fromisoformat(f["end"]) if f.get("end") else None, main_bs=f["main_bs"], check=f["check"])
        for f in data["festivals"])
    covers = data["covers"]
    return tuple(sorted(festivals, key=lambda f: f.main)), date.fromisoformat(covers["from"]), date.fromisoformat(covers["to"])


def festivals() -> tuple[Festival, ...]:
    return _load()[0]


def coverage() -> tuple[date, date]:
    """First and last day for which every festival's date is known."""
    _, first, last = _load()
    return first, last


def festival_features(days: Iterable[date]) -> pd.DataFrame:
    """One row per day, columns FESTIVAL_FEATURES. NaN outside the covered years."""
    days = list(days)
    first, last = coverage()
    mains = {key: [f.main for f in festivals() if f.key == key] for key in MAJOR}
    windows = [(f.key, *f.window) for f in festivals()]
    rows = []
    for day in days:
        if not first <= day <= last:
            rows.append([np.nan] * len(FESTIVAL_FEATURES))
            continue
        row = []
        for key in MAJOR:
            ahead = [(m - day).days for m in mains[key] if m >= day]
            # The next main day may fall after the covered years: only "far away" is safe to say then.
            row.append(float(min(ahead[0], DAYS_CAP)) if ahead else (DAYS_CAP if (last - day).days >= DAYS_CAP else np.nan))
        for key in MAJOR:
            row.append(float(any(k == key and a <= day <= b for k, a, b in windows)))
        row.append(float(any(k not in MAJOR and a <= day <= b for k, a, b in windows)))
        rows.append(row)
    return pd.DataFrame(rows, columns=FESTIVAL_FEATURES, index=pd.Index(days, name="day"))


def upcoming(day: date, within_days: int) -> list[Festival]:
    """Festivals whose build-up starts within `within_days` from `day` (or has already started)."""
    horizon = day + timedelta(days=within_days)
    return [f for f in festivals() if f.window[1] >= day and f.window[0] <= horizon]


def previous(festival: Festival) -> Festival | None:
    """The same festival one occurrence earlier (e.g. last year's Tihar), if its date is known."""
    earlier = [f for f in festivals() if f.key == festival.key and f.main < festival.main]
    return earlier[-1] if earlier else None
