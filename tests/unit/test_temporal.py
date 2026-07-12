"""Temporal kernel tests. CLAUDE.md sections 5.3 and 17.

Covers DST spring-forward (nonexistent) and fall-back (ambiguous) local times, plus
local-hour flooring and the gap-free hourly index across transitions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pipelines.features.temporal import (
    classify_local,
    dense_hourly_index,
    localize,
    to_local_hour,
)

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# US DST 2026: spring forward 2026-03-08 02:00->03:00; fall back 2026-11-01 02:00->01:00.


def test_normal_local_time():
    naive = datetime(2026, 6, 15, 14, 30)
    aware, status = localize(naive, NY)
    assert status == "normal"
    assert aware.utcoffset() == timedelta(hours=-4)  # EDT


def test_spring_forward_nonexistent_is_shifted_not_dropped():
    # 02:30 does not exist on 2026-03-08.
    naive = datetime(2026, 3, 8, 2, 30)
    assert classify_local(naive, NY) == "nonexistent"
    aware, status = localize(naive, NY)
    assert status == "nonexistent"
    # Shifted forward across the one-hour gap to a valid instant.
    assert aware.hour == 3
    assert aware.utcoffset() == timedelta(hours=-4)  # now EDT


def test_fall_back_ambiguous_resolves_to_earlier():
    # 01:30 occurs twice on 2026-11-01.
    naive = datetime(2026, 11, 1, 1, 30)
    assert classify_local(naive, NY) == "ambiguous"
    aware, status = localize(naive, NY)
    assert status == "ambiguous"
    # Earlier occurrence is EDT (-04:00), the fold=0 branch.
    assert aware.utcoffset() == timedelta(hours=-4)


def test_to_local_hour_floors_in_local_tz():
    aware_utc = datetime(2026, 6, 15, 18, 47, tzinfo=UTC)
    floored = to_local_hour(aware_utc, NY)
    assert (floored.hour, floored.minute, floored.second) == (14, 0, 0)
    assert floored.utcoffset() == timedelta(hours=-4)


def test_dense_index_is_gap_free_and_ordered():
    hours = [
        datetime(2026, 6, 15, 10, tzinfo=NY),
        datetime(2026, 6, 15, 13, tzinfo=NY),  # gap at 11 and 12
    ]
    index = dense_hourly_index(hours, NY)
    assert len(index) == 4  # 10, 11, 12, 13
    assert index == sorted(index)


def test_dense_index_reflects_dst_day_lengths():
    # Buckets from local midnight to the next local midnight (inclusive endpoints).
    def day_buckets(y: int, m: int, d0: int, d1: int) -> int:
        hours = [datetime(y, m, d0, 0, tzinfo=NY), datetime(y, m, d1, 0, tzinfo=NY)]
        return len(dense_hourly_index(hours, NY))

    normal = day_buckets(2026, 6, 15, 16)  # 24h span -> 25 inclusive buckets
    fall_back = day_buckets(2026, 11, 1, 2)  # 25h span (extra hour)
    spring_fwd = day_buckets(2026, 3, 8, 9)  # 23h span (missing hour)

    assert fall_back == normal + 1
    assert spring_fwd == normal - 1
