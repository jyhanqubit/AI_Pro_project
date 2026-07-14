"""V1-06 anomaly detection + root-cause tests (V1_Prompt §12 acceptance)."""

from __future__ import annotations

from contracts.v1.enums import AnomalyType, RootCauseStatus
from ml.anomaly import attribute_root_cause, detect_all
from ml.anomaly.scenario import build_demo_scenario


def test_detects_all_injected_fault_types() -> None:
    obs, _ = build_demo_scenario()
    alerts = detect_all(obs)
    types = {a.anomaly_type for a in alerts}
    # stale feed + impossible capacity => data_quality; sudden depletion => inventory;
    # forecast residual => forecast_residual (§12 acceptance).
    assert AnomalyType.DATA_QUALITY in types
    assert AnomalyType.INVENTORY in types
    assert AnomalyType.FORECAST_RESIDUAL in types
    # every injected fault is flagged synthetic (never mistaken for a real incident).
    assert all(a.is_synthetic_fault for a in alerts)


def test_stale_feed_and_impossible_capacity_flagged() -> None:
    obs, _ = build_demo_scenario()
    alerts = detect_all(obs)
    detectors = {a.detector for a in alerts}
    assert "freshness_rule" in detectors  # stale feed
    assert "capacity_rule" in detectors  # impossible capacity


def test_sudden_depletion_is_explained_by_event() -> None:
    obs, events = build_demo_scenario()
    alerts = attribute_root_cause(detect_all(obs), events)
    cityhall = next(
        a for a in alerts
        if a.station_id == "JC_CITYHALL" and a.anomaly_type == AnomalyType.INVENTORY
    )
    assert cityhall.root_cause_status == RootCauseStatus.EXPLAINED_BY_EVENT
    assert cityhall.linked_event_ids == ["evt_transit_cityhall"]
    assert cityhall.evidence_article_ids == ["a2"]  # provenance to the source article


def test_data_quality_is_not_event_attributed() -> None:
    obs, events = build_demo_scenario()
    alerts = attribute_root_cause(detect_all(obs), events)
    for a in alerts:
        if a.anomaly_type == AnomalyType.DATA_QUALITY:
            assert a.root_cause_status == RootCauseStatus.LIKELY_DATA_QUALITY
            assert a.linked_event_ids == []  # a stale feed is never "caused" by an event


def test_no_false_alerts_on_clean_data() -> None:
    obs, _ = build_demo_scenario()
    clean = [o for o in obs if not o.is_synthetic_fault]
    # The clean baseline (mild stable fluctuation) must not trip any detector.
    assert detect_all(clean) == []
