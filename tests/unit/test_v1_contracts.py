"""V1-00 contract tests. Validates the claim boundary and backward compatibility (V1_Prompt §6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from contracts.enums import (
    EffectDirection,
    EventType,
    ExtractionStatus,
    OperatingMode,  # v0
    TargetName,
)
from contracts.v1 import (
    AnomalyAlert,
    ArticleRecord,
    EventRecordV1,
    ExperimentDefinition,
    ExposureLog,
    ForecastPair,
    IncentiveQuote,
    OutcomeLog,
    RecommendationRequest,
    RecommendationResult,
    ScoredForecastPair,
)
from contracts.v1.enums import ClaimState, OperatingModeV1

TZ = timezone(timedelta(hours=-4))
T0 = datetime(2026, 7, 12, 13, 0, tzinfo=TZ)


def test_v1_modes_are_superset_of_v0() -> None:
    """The v0 four modes must parse unchanged under OperatingModeV1 (invariant 12)."""
    for m in OperatingMode:
        if m.value in {mv.value for mv in OperatingModeV1}:
            assert OperatingModeV1(m.value).value == m.value
    # v0 shares demo_fixture / historical_replay / research; V1 adds three serving modes.
    assert {"live_shadow", "policy_simulation", "experiment_dry_run"} <= {
        m.value for m in OperatingModeV1
    }


def test_claim_states_present() -> None:
    assert {"measured", "pending", "simulated", "dry_run"} <= {c.value for c in ClaimState}


def _article(available_at: datetime) -> ArticleRecord:
    return ArticleRecord(
        article_id="a1",
        title="PATH signal failure",
        source="fixture",
        url_hash="u1",
        title_hash="t1",
        published_at=T0,
        first_seen_at=T0,
        available_at=available_at,
        fetched_at=T0,
        ingested_at=T0,
        raw_payload_path="data/raw/a1.json",
        mode=OperatingModeV1.HISTORICAL_REPLAY,
    )


def test_article_availability_rule() -> None:
    _article(T0)  # ok: available_at == max(published, first_seen)
    with pytest.raises(ValidationError):
        _article(T0 - timedelta(minutes=1))  # before availability → reject (§5.2)


def test_event_requires_evidence() -> None:
    kw = dict(
        event_id="e1",
        source_article_ids=["a1"],
        event_type=EventType.TRANSIT_DISRUPTION,
        event_title="PATH suspended",
        published_at=T0,
        first_seen_at=T0,
        available_at=T0,
        demand_effect=EffectDirection.INCREASE,
        severity=0.7,
        confidence=0.7,
        extraction_model="mock",
        extraction_prompt_version="v1",
        status=ExtractionStatus.ACCEPTED,
        mode=OperatingModeV1.HISTORICAL_REPLAY,
    )
    EventRecordV1(evidence_spans=["signal failure suspends PATH"], **kw)
    with pytest.raises(ValidationError):
        EventRecordV1(evidence_spans=[], **kw)  # empty evidence → reject (§6.3)


def _pair(claim: ClaimState) -> ForecastPair:
    return ForecastPair(
        zone_id="892a107216bffff",
        forecast_cutoff=T0,
        forecast_horizon=1,
        target_name=TargetName.DEPARTURES,
        model_version="m1-fixture",
        feature_version="gfv1",
        train_window_id="tw1",
        seed=42,
        m0_baseline=8.0,
        m1_event_aware=11.0,
        m1_zero=8.0,
        source_event_ids=["e1"],
        claim_state=claim,
        mode=OperatingModeV1.HISTORICAL_REPLAY,
    )


def test_forecast_pair_event_delta_is_m1_minus_zero() -> None:
    assert _pair(ClaimState.PENDING).event_delta == pytest.approx(3.0)


def test_scored_pair_measured_requires_actual() -> None:
    with pytest.raises(ValidationError):
        ScoredForecastPair(pair=_pair(ClaimState.MEASURED))  # measured but no actual
    ScoredForecastPair(
        pair=_pair(ClaimState.MEASURED),
        actual=10.5,
        label_source="trip_history",
        scored_at=T0,
    )
    # pending pair may have no label
    ScoredForecastPair(pair=_pair(ClaimState.PENDING))


def test_recommendation_feasibility_and_no_candidate() -> None:
    from contracts.v1.recommendation import ScoredStation

    ok = ScoredStation(station_id="JC_GROVE", rank=1, distance_km=0.4, detour_km=0.1,
                       feasible=True, final_policy_score=1.2)
    RecommendationResult(
        request_id="r1", mode="rent", cutoff=T0,
        retriever_version="ret-v1", reranker_version="rr-v1",
        stations=[ok], claim_state=ClaimState.SIMULATED,
        operating_mode=OperatingModeV1.POLICY_SIMULATION,
    )
    bad = ScoredStation(station_id="X", rank=1, distance_km=9.0, detour_km=9.0,
                        feasible=False, final_policy_score=-1.0)
    with pytest.raises(ValidationError):  # infeasible must be removed, not surfaced
        RecommendationResult(
            request_id="r2", mode="rent", cutoff=T0,
            retriever_version="ret-v1", reranker_version="rr-v1",
            stations=[bad], claim_state=ClaimState.SIMULATED,
            operating_mode=OperatingModeV1.POLICY_SIMULATION,
        )
    with pytest.raises(ValidationError):  # no_feasible_candidate must return empty list
        RecommendationResult(
            request_id="r3", mode="rent", cutoff=T0,
            retriever_version="ret-v1", reranker_version="rr-v1",
            stations=[ok], no_feasible_candidate=True, claim_state=ClaimState.SIMULATED,
            operating_mode=OperatingModeV1.POLICY_SIMULATION,
        )


def test_incentive_is_simulated_by_default() -> None:
    q = IncentiveQuote(station_id="JC_GROVE", credit=1.0)
    assert q.is_simulated is True
    assert "SIMULATED OUTCOME" in q.disclaimer


def test_experiment_contracts_roundtrip() -> None:
    exp = ExperimentDefinition(
        experiment_id="x1", hypothesis="dynamic credit reduces shortage",
        arms=["control", "dynamic_credit"], seed=42,
        status="simulated_experiment", created_at=T0,
        mode=OperatingModeV1.EXPERIMENT_DRY_RUN,
    )
    assert exp.randomization_unit == "zone_cluster_x_time_block"
    ExposureLog(experiment_id="x1", unit_id="cl1:tb1", arm="control", assigned_at=T0)
    o = OutcomeLog(experiment_id="x1", unit_id="cl1:tb1", arm="control",
                   metric_name="shortage_minutes", metric_value=12.0, observed_at=T0)
    assert o.is_simulated is True


def test_anomaly_synthetic_flag() -> None:
    a = AnomalyAlert(
        anomaly_id="an1", detector="rolling_z@v1", anomaly_type="inventory",
        station_id="JC_HOBOKEN", detected_at=T0, window_start=T0, window_end=T0,
        score=4.2, severity=0.8, root_cause_status="inventory_dislocation",
        is_synthetic_fault=True, claim_state=ClaimState.MEASURED,
        mode=OperatingModeV1.LIVE_SHADOW,
    )
    assert a.is_synthetic_fault is True


def test_recommendation_request_bounds() -> None:
    RecommendationRequest(
        request_id="q1", mode="return", origin_lat=40.72, origin_lng=-74.04,
        cutoff=T0, operating_mode=OperatingModeV1.DEMO_FIXTURE,
    )
    with pytest.raises(ValidationError):
        RecommendationRequest(
            request_id="q2", mode="return", origin_lat=200.0, origin_lng=-74.04,
            cutoff=T0, operating_mode=OperatingModeV1.DEMO_FIXTURE,
        )
