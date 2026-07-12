"""Contract validation tests. CLAUDE.md sections 6, 5.2, 8, 17.

These lock in the non-negotiable invariants: timezone-awareness, the availability rule,
the accepted-event evidence requirement, and optional forecast intervals.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from contracts import (
    ArticleRecord,
    EventExtraction,
    EvidenceSpan,
    FeatureSnapshot,
    ForecastOutput,
    OperatingMode,
    TripRecord,
)
from contracts.enums import EventType, ExtractionStatus, TargetName

T0 = datetime(2026, 7, 12, 14, 0, tzinfo=UTC)
NAIVE = datetime(2026, 7, 12, 14, 0)  # deliberately timezone-naive


# --- Trip -----------------------------------------------------------------


def _trip(**overrides):
    base = dict(
        trip_id="t1",
        started_at=T0,
        ended_at=T0 + timedelta(minutes=10),
        start_station_id="s1",
        end_station_id="s2",
        start_lat=40.7,
        start_lng=-74.0,
        end_lat=40.8,
        end_lng=-73.9,
        source_file="rides.csv",
        loaded_at=T0,
    )
    base.update(overrides)
    return TripRecord(**base)


def test_trip_valid():
    assert _trip().trip_id == "t1"


def test_trip_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        _trip(started_at=NAIVE)


def test_trip_rejects_end_before_start():
    with pytest.raises(ValidationError):
        _trip(ended_at=T0 - timedelta(minutes=1))


def test_trip_rejects_out_of_range_coords():
    with pytest.raises(ValidationError):
        _trip(start_lat=100.0)


def test_trip_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _trip(rider_name="alice")


# --- Article: availability rule (section 5.2) -----------------------------


def _article(**overrides):
    base = dict(
        article_id="a1",
        title="Signal problems on the L train",
        text="MTA reports major delays.",
        source="demo",
        published_at=T0,
        first_seen_at=T0 - timedelta(hours=1),
        url_hash="deadbeef",
        mode=OperatingMode.DEMO_FIXTURE,
        raw_payload_path="data/fixtures/a1.json",
    )
    base.update(overrides)
    return ArticleRecord(**base)


def test_article_available_at_computed_as_max():
    art = _article()  # published later than first_seen
    assert art.available_at == T0


def test_article_available_at_uses_first_seen_when_later():
    later = T0 + timedelta(hours=2)
    art = _article(first_seen_at=later)
    assert art.available_at == later


def test_article_rejects_inconsistent_available_at():
    with pytest.raises(ValidationError):
        _article(available_at=T0 - timedelta(hours=5))


# --- Event extraction: evidence + provenance (section 8) ------------------


def _event(**overrides):
    base = dict(
        event_id="e1",
        source_article_ids=["a1"],
        event_type=EventType.TRANSIT_DISRUPTION,
        event_title="L train suspended",
        event_summary="Service suspended between stations.",
        published_at=T0,
        first_seen_at=T0,
        severity=0.6,
        confidence=0.8,
        evidence_spans=[EvidenceSpan(article_id="a1", text="Service suspended")],
        extraction_model="mock-v0",
        extraction_prompt_version="p0",
        status=ExtractionStatus.ACCEPTED,
    )
    base.update(overrides)
    return EventExtraction(**base)


def test_event_valid_accepted():
    assert _event().available_at == T0


def test_accepted_event_requires_evidence():
    with pytest.raises(ValidationError):
        _event(evidence_spans=[])


def test_accepted_event_requires_provenance():
    with pytest.raises(ValidationError):
        _event(source_article_ids=[])


def test_rejected_event_may_lack_evidence():
    # Rejected/quarantined extractions stay auditable without full completeness.
    ev = _event(status=ExtractionStatus.REJECTED, evidence_spans=[], source_article_ids=[])
    assert ev.status is ExtractionStatus.REJECTED


def test_event_rejects_severity_out_of_bounds():
    with pytest.raises(ValidationError):
        _event(severity=1.5)


def test_event_rejects_end_before_start():
    with pytest.raises(ValidationError):
        _event(event_start_at=T0, event_end_at=T0 - timedelta(hours=1))


# --- Feature snapshot -----------------------------------------------------


def test_feature_snapshot_valid():
    snap = FeatureSnapshot(
        zone_id="z1",
        forecast_cutoff=T0,
        feature_version="fv1",
        source_event_ids=["e1"],
        features={"event_count_6h_by_type": 2.0},
        created_at=T0,
    )
    assert snap.features["event_count_6h_by_type"] == 2.0


# --- Forecast output: optional intervals + delta --------------------------


def _forecast(**overrides):
    base = dict(
        zone_id="z1",
        forecast_cutoff=T0,
        forecast_horizon=1,
        model_version="m1",
        feature_version="fv1",
        target_name=TargetName.DEPARTURES,
        baseline_forecast=10.0,
        event_aware_forecast=14.0,
        mode=OperatingMode.HISTORICAL_REPLAY,
    )
    base.update(overrides)
    return ForecastOutput(**base)


def test_forecast_delta_is_computed_when_omitted():
    assert _forecast().forecast_delta == pytest.approx(4.0)


def test_forecast_intervals_optional():
    fc = _forecast()
    assert fc.p10 is None and fc.p50 is None and fc.p90 is None


def test_forecast_rejects_disordered_quantiles():
    with pytest.raises(ValidationError):
        _forecast(p10=5.0, p50=3.0, p90=9.0)


def test_forecast_horizon_must_be_positive():
    with pytest.raises(ValidationError):
        _forecast(forecast_horizon=0)
