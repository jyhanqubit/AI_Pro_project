"""V1-02 incremental graph-feature refresh tests (V1_Prompt §8 acceptance).

Incremental refresh must equal a full rebuild, and a future (post-cutoff) event must never leak
into a snapshot.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.features import build_graph_features
from pipelines.features.incremental import affected_zones, refresh_incremental

CUTOFF = datetime.fromisoformat("2026-07-12T15:30:00-04:00")  # all demo events available
STAMP = datetime.fromisoformat("2026-07-12T00:00:00-04:00")


@pytest.fixture
def demo():
    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))
    return events, articles


def _by_zone(snaps):
    return {s.zone_id: s for s in snaps}


def _assert_equivalent(a_snaps, b_snaps):
    a, b = _by_zone(a_snaps), _by_zone(b_snaps)
    assert set(a) == set(b), "zone sets differ"
    for z in a:
        assert a[z].source_event_ids == b[z].source_event_ids, f"source ids differ @ {z}"
        fa, fb = a[z].features, b[z].features
        assert set(fa) == set(fb), f"feature keys differ @ {z}"
        for k in fa:
            assert fa[k] == pytest.approx(fb[k]), f"feature {k} differs @ {z}"


def test_incremental_equals_full_rebuild_new_zone(demo) -> None:
    events, articles = demo
    base, new = events[:-1], events[-1:]
    base_snaps = build_graph_features(base, articles, forecast_cutoff=CUTOFF, created_at=STAMP)
    incremental = refresh_incremental(
        base_snaps, events, articles, forecast_cutoff=CUTOFF, new_events=new, created_at=STAMP
    )
    full = build_graph_features(events, articles, forecast_cutoff=CUTOFF, created_at=STAMP)
    _assert_equivalent(incremental, full)


def test_incremental_equals_full_rebuild_same_zone(demo) -> None:
    """A new event in an already-known zone must trigger a recompute equal to the full build."""
    events, articles = demo
    # Duplicate an existing event into the same location with a fresh id (same zone recompute path).
    twin = events[0].model_copy(update={"event_id": events[0].event_id + "_twin"})
    all_events = events + [twin]
    base_snaps = build_graph_features(events, articles, forecast_cutoff=CUTOFF, created_at=STAMP)
    incremental = refresh_incremental(
        base_snaps, all_events, articles, forecast_cutoff=CUTOFF,
        new_events=[twin], created_at=STAMP,
    )
    full = build_graph_features(all_events, articles, forecast_cutoff=CUTOFF, created_at=STAMP)
    _assert_equivalent(incremental, full)


def test_future_event_does_not_leak(demo) -> None:
    """Refreshing with an event whose available_at > cutoff changes nothing (leakage guard §5.2)."""
    events, articles = demo
    early = datetime.fromisoformat("2026-07-12T13:59:00-04:00")  # before the 14:00 transit event
    base = [e for e in events if e.available_at is not None and e.available_at <= early]
    base_snaps = build_graph_features(base, articles, forecast_cutoff=early, created_at=STAMP)
    future = [e for e in events if e.available_at is not None and e.available_at > early]
    incremental = refresh_incremental(
        base_snaps, events, articles, forecast_cutoff=early, new_events=future, created_at=STAMP
    )
    full = build_graph_features(events, articles, forecast_cutoff=early, created_at=STAMP)
    _assert_equivalent(incremental, full)  # future events contribute zero at this cutoff


def test_affected_zones_includes_new_event_zone(demo) -> None:
    events, _ = demo
    aff = affected_zones(events[-1:], known_zones=[])
    assert len(aff) >= 1  # at least the new event's own zone
