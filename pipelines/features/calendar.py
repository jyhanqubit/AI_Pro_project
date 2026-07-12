"""Calendar features. CLAUDE.md section 11.2 (ablation B1 = demand history + calendar).

These features describe the *target* hour, which is always known at forecast time, so they
carry no leakage and need no shifting. Includes cyclical encodings and US federal holidays,
computed with a small self-contained calculator (no external dependency, fully deterministic).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from functools import lru_cache

from config.features import EVENING_RUSH_HOURS, MORNING_RUSH_HOURS


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th (1-based) occurrence of ``weekday`` (Mon=0) in a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return date(year, month, 1 + offset + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """The last occurrence of ``weekday`` (Mon=0) in a month."""
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


@lru_cache(maxsize=32)
def us_federal_holidays(year: int) -> frozenset[date]:
    """US federal holidays for a year (observed-date shifting is intentionally omitted)."""
    return frozenset(
        {
            date(year, 1, 1),  # New Year's Day
            _nth_weekday(year, 1, 0, 3),  # MLK Day (3rd Mon Jan)
            _nth_weekday(year, 2, 0, 3),  # Washington's Birthday (3rd Mon Feb)
            _last_weekday(year, 5, 0),  # Memorial Day (last Mon May)
            date(year, 6, 19),  # Juneteenth
            date(year, 7, 4),  # Independence Day
            _nth_weekday(year, 9, 0, 1),  # Labor Day (1st Mon Sep)
            _nth_weekday(year, 10, 0, 2),  # Columbus Day (2nd Mon Oct)
            date(year, 11, 11),  # Veterans Day
            _nth_weekday(year, 11, 3, 4),  # Thanksgiving (4th Thu Nov)
            date(year, 12, 25),  # Christmas
        }
    )


def calendar_features(hour_start: datetime) -> dict[str, float]:
    """Leakage-free calendar features for the target local hour."""
    hour = hour_start.hour
    dow = hour_start.weekday()  # Mon=0 .. Sun=6
    return {
        "cal_hour_of_day": float(hour),
        "cal_day_of_week": float(dow),
        "cal_is_weekend": float(dow >= 5),
        "cal_is_morning_rush": float(hour in MORNING_RUSH_HOURS),
        "cal_is_evening_rush": float(hour in EVENING_RUSH_HOURS),
        "cal_is_holiday": float(hour_start.date() in us_federal_holidays(hour_start.year)),
        # Cyclical encodings so hour 23 and hour 0 are adjacent, likewise Sun and Mon.
        "cal_hour_sin": math.sin(2 * math.pi * hour / 24),
        "cal_hour_cos": math.cos(2 * math.pi * hour / 24),
        "cal_dow_sin": math.sin(2 * math.pi * dow / 7),
        "cal_dow_cos": math.cos(2 * math.pi * dow / 7),
    }
