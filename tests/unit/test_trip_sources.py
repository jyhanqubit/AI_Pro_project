"""Multi-file trip-source resolution for the forecasting panel (CLAUDE.md §11, §17).

``resolve_trip_sources`` lets one run combine many monthly archives into a single demand panel. It
only inspects paths (never reads them), so these use empty temp files. Pins: single file, explicit
list, directory scan, and the de-duplication of a month present as both ``.zip`` and extracted
``.csv`` (so it is not counted twice).
"""

from __future__ import annotations

from pathlib import Path

from config.collectors import CITIBIKE_SAMPLE_FIXTURE
from ml.forecasting.dataset import resolve_trip_sources


def test_none_falls_back_to_sample_fixture() -> None:
    assert resolve_trip_sources(None) == [CITIBIKE_SAMPLE_FIXTURE]


def test_single_file_str_or_path() -> None:
    assert resolve_trip_sources("data/x/202601-citibike-tripdata.zip") == [
        Path("data/x/202601-citibike-tripdata.zip")
    ]


def test_explicit_list_is_sorted_and_deduped() -> None:
    got = resolve_trip_sources(
        [
            "b/202602-citibike-tripdata.zip",
            "a/202601-citibike-tripdata.zip",
            "a/202601-citibike-tripdata.zip",  # duplicate
        ]
    )
    assert got == [
        Path("a/202601-citibike-tripdata.zip"),
        Path("b/202602-citibike-tripdata.zip"),
    ]


def test_directory_scan_collects_zip_and_csv(tmp_path: Path) -> None:
    (tmp_path / "202601-citibike-tripdata.zip").write_bytes(b"")
    (tmp_path / "202602-citibike-tripdata.csv").write_bytes(b"")  # a standalone extracted month
    (tmp_path / "readme.txt").write_text("ignore me")  # non-trip file ignored
    got = resolve_trip_sources(tmp_path)
    assert got == [
        tmp_path / "202601-citibike-tripdata.zip",
        tmp_path / "202602-citibike-tripdata.csv",
    ]


def test_directory_dedupes_zip_and_its_extracted_csv(tmp_path: Path) -> None:
    # A month present as BOTH the archive and its extracted CSV must be counted once (the zip wins).
    (tmp_path / "202601-citibike-tripdata.zip").write_bytes(b"")
    (tmp_path / "202601-citibike-tripdata.csv").write_bytes(b"")  # extracted from the zip above
    (tmp_path / "JC-202606-citibike-tripdata.csv.zip").write_bytes(b"")
    (tmp_path / "JC-202606-citibike-tripdata.csv").write_bytes(b"")  # extracted from the .csv.zip
    got = resolve_trip_sources(tmp_path)
    assert got == [
        tmp_path / "202601-citibike-tripdata.zip",
        tmp_path / "JC-202606-citibike-tripdata.csv.zip",
    ]
