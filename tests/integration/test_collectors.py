"""Collector integration tests. CLAUDE.md sections 7 and 17.

Exercises fixture-to-record collection for all three MVP sources, offline. Covers the
golden-path availability boundary (13:59 -> 14:00) and exclusion accounting.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from config.collectors import (
    CITIBIKE_SAMPLE_FIXTURE,
    GBFS_STATION_STATUS_FIXTURE,
    NEWS_DEMO_FIXTURE,
)
from contracts.enums import OperatingMode
from pipelines.collectors import (
    CitiBikeCollector,
    GbfsStationStatusCollector,
    NewsFixtureCollector,
    NewsFixtureError,
)

# --- Citi Bike ------------------------------------------------------------


def test_citibike_accepts_valid_and_counts_exclusions():
    result = CitiBikeCollector(CITIBIKE_SAMPLE_FIXTURE).collect()
    meta = result.metadata

    assert meta.total_rows == 7
    assert meta.accepted_rows == 4
    assert meta.excluded_rows == 3
    assert len(result.records) == 4
    # Every bad row is accounted for by an explicit reason (section 6.1).
    assert sum(meta.exclusion_reasons.values()) == 3
    assert "end_before_start" in meta.exclusion_reasons
    assert "coordinate_out_of_range" in meta.exclusion_reasons
    assert meta.schema_hash is not None


def test_citibike_timestamps_are_timezone_aware():
    result = CitiBikeCollector(CITIBIKE_SAMPLE_FIXTURE).collect()
    for trip in result.records:
        assert trip.started_at.tzinfo is not None
        assert trip.ended_at.tzinfo is not None
        assert trip.ended_at >= trip.started_at


# --- Demo news fixture ----------------------------------------------------


def test_news_dedup_and_replay_order():
    result = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect()
    meta = result.metadata

    assert meta.total_rows == 4
    assert meta.accepted_rows == 3  # one duplicate article_id removed
    assert meta.exclusion_reasons.get("duplicate_article") == 1
    assert [a.article_id for a in result.records] == ["a1", "a2", "a3"]

    # Strictly ordered by available_at.
    availables = [a.available_at for a in result.records]
    assert availables == sorted(availables)


def test_news_golden_boundary_availability():
    result = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect()
    collector = NewsFixtureCollector(NEWS_DEMO_FIXTURE)

    cutoff_1359 = datetime.fromisoformat("2026-07-12T13:59:00-04:00")
    cutoff_1400 = datetime.fromisoformat("2026-07-12T14:00:00-04:00")

    before = {a.article_id for a in collector.available_at_cutoff(result.records, cutoff_1359)}
    after = {a.article_id for a in collector.available_at_cutoff(result.records, cutoff_1400)}

    # The signal-failure event (a2) becomes available exactly at 14:00.
    assert "a2" not in before
    assert "a2" in after


def test_news_invalid_timestamp_fails_precisely(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"article_id": "x", "title": "t", "text": "t", "source": "s", '
        '"published_at": "not-a-timestamp", "first_seen_at": "2026-07-12T13:00:00-04:00", '
        '"url_hash": "h"}\n',
        encoding="utf-8",
    )
    with pytest.raises(NewsFixtureError, match="invalid timestamp"):
        NewsFixtureCollector(bad).collect()


# --- GBFS station status --------------------------------------------------


def test_gbfs_fixture_mode_offline():
    result = GbfsStationStatusCollector(GBFS_STATION_STATUS_FIXTURE).collect()
    meta = result.metadata

    assert meta.mode is OperatingMode.DEMO_FIXTURE
    assert len(result.records) == 3
    assert meta.payload_hash is not None
    for station in result.records:
        assert station.fetched_at.tzinfo is not None
        assert station.source_last_updated.tzinfo is not None
        assert station.num_bikes_available >= 0


def test_gbfs_live_disabled_by_default_does_not_fetch():
    # Live is opt-in; the default constructor must not perform network I/O.
    collector = GbfsStationStatusCollector(GBFS_STATION_STATUS_FIXTURE)
    assert collector.live is False
    result = collector.collect()
    assert result.metadata.mode is OperatingMode.DEMO_FIXTURE


def test_gbfs_live_failure_returns_degraded_state():
    # Point live mode at an unroutable URL; it must degrade, not raise.
    collector = GbfsStationStatusCollector(
        GBFS_STATION_STATUS_FIXTURE,
        live=True,
        url="http://127.0.0.1:1/station_status.json",
        timeout=0.2,
        max_retries=1,
    )
    result = collector.collect()
    assert result.records == []
    assert result.metadata.warnings
    assert "degraded" in result.metadata.warnings[0]
