"""Citi Bike bulk downloader — month/key logic (V2). CLAUDE.md §7.1, §17.

The network fetch needs egress, so these pin the pure, offline-testable parts: month-range
expansion and matching a ``YYYYMM`` to the right bucket key across the naming variants (``.zip`` /
``.csv.zip`` / ``JC-`` prefix) without downloading anything.
"""

from __future__ import annotations

import pytest

from pipelines.collectors.download_citibike import find_keys_for_month, month_range

# A representative slice of the real bucket listing (naming has drifted over the years).
_KEYS = [
    "202405-citibike-tripdata.zip",
    "202406-citibike-tripdata.zip",
    "202406-citibike-tripdata.csv.zip",  # duplicate-naming edge: both should match NYC 202406
    "JC-202406-citibike-tripdata.csv.zip",
    "JC-202606-citibike-tripdata.csv.zip",
    "201509-citibike-tripdata.csv.zip",
    "index.html",
    "202406-other-dataset.zip",  # not citibike -> excluded
]


def test_month_range_inclusive_and_year_rollover() -> None:
    assert month_range("202401", "202403") == ["202401", "202402", "202403"]
    assert month_range("202411", "202502") == ["202411", "202412", "202501", "202502"]
    assert month_range("202406", "202406") == ["202406"]


def test_month_range_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        month_range("2024-06", "202407")  # not YYYYMM
    with pytest.raises(ValueError):
        month_range("202413", "202414")  # month 13
    with pytest.raises(ValueError):
        month_range("202406", "202401")  # start after end


def test_find_keys_matches_nyc_and_excludes_jc_and_noise() -> None:
    hits = find_keys_for_month(_KEYS, "202406", jersey_city=False)
    assert hits == [
        "202406-citibike-tripdata.csv.zip",
        "202406-citibike-tripdata.zip",
    ]  # sorted; both NYC naming variants, no JC, no non-citibike/non-zip


def test_find_keys_jersey_city_variant() -> None:
    assert find_keys_for_month(_KEYS, "202406", jersey_city=True) == [
        "JC-202406-citibike-tripdata.csv.zip"
    ]


def test_find_keys_absent_month_is_empty() -> None:
    assert find_keys_for_month(_KEYS, "209912", jersey_city=False) == []
