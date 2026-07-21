"""Unit tests for the improved (v2) event feature builders: time-anchoring, leakage gating,
type-scoped boroughs, and graph neighbor spillover — all on synthetic events (no trip pipeline)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ml.forecasting.event_features_v2 import (
    DIRECT_COLS,
    EventFeatureCfg,
    build_direct_index,
    build_graph_index,
    build_permitized_index,
    scoped_boroughs,
)

_NY = ZoneInfo("America/New_York")


@dataclass
class _Art:
    article_id: str
    available_at: datetime
    published_at: datetime
    first_seen_at: datetime


def _art(aid: str, iso: str) -> _Art:
    t = datetime.fromisoformat(iso).replace(tzinfo=_NY)
    return _Art(aid, t, t, t)


def test_scoping_point_event_named_only_weather_citywide():
    # A venue event named in Manhattan stays in Manhattan; a weather shock may be citywide.
    assert scoped_boroughs("LARGE_VENUE_EVENT", ["Manhattan"]) == ["Manhattan"]
    assert scoped_boroughs("PUBLIC_GATHERING", []) == []  # point event, no borough -> dropped
    assert set(scoped_boroughs("WEATHER_SHOCK", [])) == {
        "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"
    }


def test_feature_anchored_at_event_peak_not_publish_time():
    # Event on 2026-05-10 (venue -> peak 19:00), article published early that morning. The feature
    # must peak near 19:00, not at the 06:00 publish hour.
    ev = [{"article_id": "a", "d": "2026-05-10", "event_type": "LARGE_VENUE_EVENT",
           "severity": 0.8, "boroughs": ["Manhattan"]}]
    idx, diag = build_direct_index(ev, {"a": _art("a", "2026-05-10T06:00")})
    assert diag["attributed_events"] == 1
    peak = idx[("Manhattan", "2026-05-10 19")]["news_llm_active"]
    off = idx[("Manhattan", "2026-05-10 13")]["news_llm_active"]  # 6h before peak
    assert peak == 1.0                # weight is max (1.0) at the anchor
    assert 0.0 < off < peak           # decays away from the peak
    assert idx[("Manhattan", "2026-05-10 19")]["news_llm_crowd"] == 1.0


def test_leakage_gate_no_feature_before_available_at():
    # Article only public at 2026-05-10 20:00; hours before that must carry no feature even though
    # the event peak (19:00) precedes availability.
    ev = [{"article_id": "a", "d": "2026-05-10", "event_type": "LARGE_VENUE_EVENT",
           "severity": 0.8, "boroughs": ["Manhattan"]}]
    idx, _ = build_direct_index(ev, {"a": _art("a", "2026-05-10T20:00")})
    assert ("Manhattan", "2026-05-10 19") not in idx      # before availability -> absent
    assert ("Manhattan", "2026-05-10 18") not in idx
    assert idx[("Manhattan", "2026-05-10 20")]["news_llm_active"] > 0  # first available hour present


def test_point_event_does_not_pollute_all_boroughs():
    ev = [{"article_id": "a", "d": "2026-05-10", "event_type": "LARGE_VENUE_EVENT",
           "severity": 0.8, "boroughs": ["Manhattan"]}]
    idx, _ = build_direct_index(ev, {"a": _art("a", "2026-05-10T06:00")})
    touched = {b for (b, _hk) in idx}
    assert touched == {"Manhattan"}  # only the host borough in the DIRECT arm


def test_graph_spillover_reaches_neighbors_and_decays_with_distance():
    # Manhattan venue event -> neighbor feature in OTHER boroughs, larger for closer ones.
    ev = [{"article_id": "a", "d": "2026-05-10", "event_type": "LARGE_VENUE_EVENT",
           "severity": 1.0, "boroughs": ["Manhattan"]}]
    gidx = build_graph_index(ev, {"a": _art("a", "2026-05-10T06:00")})
    bronx = gidx[("Bronx", "2026-05-10 19")]["news_llm_neighbor"]        # ~8 km
    staten = gidx[("Staten Island", "2026-05-10 19")]["news_llm_neighbor"]  # ~20 km
    assert bronx > 0 and staten > 0
    assert bronx > staten                                   # closer borough -> stronger spillover
    assert ("Manhattan", "2026-05-10 19") not in gidx       # host borough not in the graph arm


def test_graph_feature_also_leakage_gated():
    ev = [{"article_id": "a", "d": "2026-05-10", "event_type": "LARGE_VENUE_EVENT",
           "severity": 1.0, "boroughs": ["Manhattan"]}]
    gidx = build_graph_index(ev, {"a": _art("a", "2026-05-10T20:00")})
    assert ("Bronx", "2026-05-10 18") not in gidx           # before availability
    assert gidx[("Bronx", "2026-05-10 20")]["news_llm_neighbor"] > 0


def test_permitized_spans_precise_interval_and_is_active_throughout():
    # Precise start/end -> feature active (weight 1.0) across the whole event interval, not a peak.
    ev = [{"article_id": "a", "event_type": "TRANSIT_DISRUPTION", "severity": 0.8,
           "boroughs": ["Manhattan", "Queens"],
           "event_start_at": "2026-05-16T04:00:00-04:00", "event_end_at": "2026-05-16T23:00:00-04:00"}]
    idx, diag = build_permitized_index(ev, {"a": _art("a", "2026-05-16T04:00")})
    assert diag["attributed_events"] == 1 and diag["leakage_dropped"] == 0
    assert idx[("Manhattan", "2026-05-16 06")]["news_llm_active"] == 1.0
    assert idx[("Queens", "2026-05-16 20")]["news_llm_active"] == 1.0
    assert idx[("Manhattan", "2026-05-16 06")]["news_llm_transit"] == 1.0
    assert ("Bronx", "2026-05-16 06") not in idx  # not an attributed borough


def test_permitized_retrospective_review_self_excludes_by_leakage():
    # A show at 20:00 reviewed/published the NEXT afternoon -> event entirely before availability ->
    # the whole record drops out (leakage), which is the honest timing gap vs advance permits.
    ev = [{"article_id": "a", "event_type": "LARGE_VENUE_EVENT", "severity": 0.4,
           "boroughs": ["Brooklyn"],
           "event_start_at": "2026-05-07T20:00:00-04:00", "event_end_at": "2026-05-07T23:00:00-04:00"}]
    idx, diag = build_permitized_index(ev, {"a": _art("a", "2026-05-08T15:28")})
    assert diag["leakage_dropped"] == 1
    assert diag["attributed_events"] == 0
    assert len(idx) == 0
