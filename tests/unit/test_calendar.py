"""Calendar feature tests. CLAUDE.md sections 11.2 and 17."""

from __future__ import annotations

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pipelines.features.calendar import calendar_features, us_federal_holidays

NY = ZoneInfo("America/New_York")


def test_hour_and_weekday():
    # 2026-06-15 is a Monday.
    f = calendar_features(datetime(2026, 6, 15, 8, tzinfo=NY))
    assert f["cal_hour_of_day"] == 8.0
    assert f["cal_day_of_week"] == 0.0  # Monday
    assert f["cal_is_weekend"] == 0.0
    assert f["cal_is_morning_rush"] == 1.0
    assert f["cal_is_evening_rush"] == 0.0


def test_weekend_and_evening_rush():
    # 2026-06-20 is a Saturday.
    f = calendar_features(datetime(2026, 6, 20, 17, tzinfo=NY))
    assert f["cal_day_of_week"] == 5.0
    assert f["cal_is_weekend"] == 1.0
    assert f["cal_is_evening_rush"] == 1.0


def test_cyclical_encoding_wraps():
    midnight = calendar_features(datetime(2026, 6, 15, 0, tzinfo=NY))
    assert math.isclose(midnight["cal_hour_sin"], 0.0, abs_tol=1e-9)
    assert math.isclose(midnight["cal_hour_cos"], 1.0, abs_tol=1e-9)
    # Hour 23 is close to hour 0 in cyclical space (adjacent on the circle).
    h23 = calendar_features(datetime(2026, 6, 15, 23, tzinfo=NY))
    dist = math.hypot(
        h23["cal_hour_sin"] - midnight["cal_hour_sin"],
        h23["cal_hour_cos"] - midnight["cal_hour_cos"],
    )
    assert dist < 0.3  # one hour apart on the unit circle


def test_us_federal_holidays_2026():
    hols = us_federal_holidays(2026)
    assert date(2026, 1, 1) in hols  # New Year's Day
    assert date(2026, 1, 19) in hols  # MLK Day (3rd Mon Jan)
    assert date(2026, 5, 25) in hols  # Memorial Day (last Mon May)
    assert date(2026, 6, 19) in hols  # Juneteenth
    assert date(2026, 7, 4) in hols  # Independence Day
    assert date(2026, 11, 26) in hols  # Thanksgiving (4th Thu Nov)
    assert date(2026, 12, 25) in hols  # Christmas
    assert date(2026, 6, 15) not in hols  # ordinary Monday


def test_is_holiday_flag():
    juneteenth = calendar_features(datetime(2026, 6, 19, 12, tzinfo=NY))
    ordinary = calendar_features(datetime(2026, 6, 18, 12, tzinfo=NY))
    assert juneteenth["cal_is_holiday"] == 1.0
    assert ordinary["cal_is_holiday"] == 0.0
