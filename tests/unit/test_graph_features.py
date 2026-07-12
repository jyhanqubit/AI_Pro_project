"""As-of graph feature tests. CLAUDE.md sections 10, 5.2, 5.4, 17.

Includes the minimum leakage regression: an event first available at 14:01 contributes
zero to features built for a 14:00 cutoff. Plus kernel math, determinism, distance decay,
config reproducibility, and provenance preservation.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from contracts.article import ArticleRecord
from contracts.enums import EventType, ExtractionStatus, OperatingMode
from contracts.event import EventExtraction, EvidenceSpan, Location
from pipelines.features import (
    GraphFeatureConfig,
    build_graph_features,
    exp_distance_decay,
    half_life_weight,
    haversine_km,
    zone_for,
    zone_neighbors,
)

HOBOKEN = (40.7360, -74.0301)


def _article(article_id: str = "a1") -> ArticleRecord:
    ts = datetime(2026, 7, 12, 14, 1, tzinfo=UTC)
    return ArticleRecord(
        article_id=article_id,
        title="t",
        text="signal failure",
        source="demo_wire",
        published_at=ts,
        first_seen_at=ts,
        url_hash=f"h_{article_id}",
        mode=OperatingMode.HISTORICAL_REPLAY,
        raw_payload_path="x",
    )


def _event(
    available_at: datetime,
    *,
    event_type: EventType = EventType.TRANSIT_DISRUPTION,
    severity: float = 0.8,
    lat: float = HOBOKEN[0],
    lng: float = HOBOKEN[1],
    event_id: str = "e1",
    confidence: float = 0.8,
    status: ExtractionStatus = ExtractionStatus.ACCEPTED,
) -> EventExtraction:
    return EventExtraction(
        event_id=event_id,
        source_article_ids=["a1"],
        event_type=event_type,
        event_title="Signal failure",
        event_summary="s",
        published_at=available_at,
        first_seen_at=available_at,
        event_start_at=available_at,
        locations=[Location(name="Hoboken Terminal", lat=lat, lng=lng)],
        severity=severity,
        confidence=confidence,
        evidence_spans=[EvidenceSpan(article_id="a1", text="signal failure")],
        extraction_model="mock-v1",
        extraction_prompt_version="mock-v1",
        status=status,
    )


# --- Kernels --------------------------------------------------------------


def test_haversine_one_degree_latitude():
    assert haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.19, rel=1e-3)
    assert haversine_km(40.0, -74.0, 40.0, -74.0) == 0.0


def test_distance_decay_monotonic():
    assert exp_distance_decay(0.0, 1.0) == 1.0
    assert exp_distance_decay(1.0, 1.0) == pytest.approx(math.exp(-1))
    assert exp_distance_decay(2.0, 1.0) < exp_distance_decay(1.0, 1.0)


def test_half_life_weight():
    assert half_life_weight(0.0, 6.0) == 1.0
    assert half_life_weight(6.0, 6.0) == pytest.approx(0.5)
    assert half_life_weight(-1.0, 6.0) == 0.0  # future events carry no weight


# --- Leakage regression (section 5.2) -------------------------------------


def test_event_available_1401_is_absent_at_1400_cutoff():
    available = datetime(2026, 7, 12, 14, 1, tzinfo=UTC)
    zone = zone_for(*HOBOKEN)
    event, articles = _event(available), [_article()]

    before = build_graph_features(
        [event], articles, forecast_cutoff=datetime(2026, 7, 12, 14, 0, tzinfo=UTC), zones=[zone]
    )[0]
    # Every event-derived feature must be zero at the 14:00 cutoff.
    assert before.features["transit_disruption_exposure"] == 0.0
    assert before.features["distance_decayed_impact"] == 0.0
    assert before.features["confidence_max"] == 0.0
    assert before.source_event_ids == []

    after = build_graph_features(
        [event], articles, forecast_cutoff=datetime(2026, 7, 12, 14, 1, tzinfo=UTC), zones=[zone]
    )[0]
    assert after.features["transit_disruption_exposure"] > 0.0
    assert after.source_event_ids == ["e1"]


# --- Determinism & provenance ---------------------------------------------


def test_deterministic_output():
    cutoff = datetime(2026, 7, 12, 15, 0, tzinfo=UTC)
    ev, arts = _event(datetime(2026, 7, 12, 14, 0, tzinfo=UTC)), [_article()]
    stamp = datetime(2026, 7, 12, tzinfo=UTC)
    a = build_graph_features(ev and [ev], arts, forecast_cutoff=cutoff, created_at=stamp)
    b = build_graph_features([ev], arts, forecast_cutoff=cutoff, created_at=stamp)
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]


def test_source_event_ids_preserved():
    cutoff = datetime(2026, 7, 12, 15, 0, tzinfo=UTC)
    snaps = build_graph_features(
        [_event(datetime(2026, 7, 12, 14, 0, tzinfo=UTC))], [_article()], forecast_cutoff=cutoff
    )
    assert snaps and "e1" in snaps[0].source_event_ids


# --- Distance radius & config reproducibility -----------------------------


def test_event_outside_radius_has_no_impact():
    cutoff = datetime(2026, 7, 12, 15, 0, tzinfo=UTC)
    ev = _event(datetime(2026, 7, 12, 14, 0, tzinfo=UTC))
    far_zone = zone_for(41.5, -73.0)  # well outside the 2 km radius
    snap = build_graph_features([ev], [_article()], forecast_cutoff=cutoff, zones=[far_zone])[0]
    assert snap.features["distance_decayed_impact"] == 0.0


def test_half_life_config_changes_impact_reproducibly():
    # Event aged 6h: a shorter half-life yields a smaller time-decayed impact.
    available = datetime(2026, 7, 12, 8, 0, tzinfo=UTC)
    cutoff = datetime(2026, 7, 12, 14, 0, tzinfo=UTC)  # 6 hours later
    zone = zone_for(*HOBOKEN)
    ev, arts = _event(available), [_article()]

    long_hl = GraphFeatureConfig(default_half_life_h=12.0, half_life_by_type={})
    short_hl = GraphFeatureConfig(default_half_life_h=3.0, half_life_by_type={})
    imp_long = build_graph_features(
        [ev], arts, forecast_cutoff=cutoff, zones=[zone], config=long_hl
    )[0].features["distance_decayed_impact"]
    imp_short = build_graph_features(
        [ev], arts, forecast_cutoff=cutoff, zones=[zone], config=short_hl
    )[0].features["distance_decayed_impact"]
    assert imp_short < imp_long


def test_low_confidence_event_excluded():
    cutoff = datetime(2026, 7, 12, 15, 0, tzinfo=UTC)
    zone = zone_for(*HOBOKEN)
    weak = _event(datetime(2026, 7, 12, 14, 0, tzinfo=UTC), confidence=0.2)
    snap = build_graph_features([weak], [_article()], forecast_cutoff=cutoff, zones=[zone])[0]
    assert snap.features["distance_decayed_impact"] == 0.0


# --- Neighbour propagation ------------------------------------------------


def test_neighbor_zone_impact_is_computed():
    # The 2 km radius spans many H3 res-9 cells, so a zone's neighbours also see a nearby
    # event: neighbour_zone_impact aggregates their decayed impact (with the hop penalty).
    cutoff = datetime(2026, 7, 12, 15, 0, tzinfo=UTC)
    ev = _event(datetime(2026, 7, 12, 14, 0, tzinfo=UTC))
    event_zone = zone_for(*HOBOKEN)
    assert zone_neighbors(event_zone, 1)  # sanity: neighbours exist
    snap = build_graph_features([ev], [_article()], forecast_cutoff=cutoff, zones=[event_zone])[0]
    assert snap.features["neighbor_zone_impact"] > 0.0
    assert snap.features["distance_decayed_impact"] > 0.0
