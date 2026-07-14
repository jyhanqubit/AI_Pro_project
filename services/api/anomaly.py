"""Anomaly Center data for the API/UI (V1_Prompt §12).

Runs the four detector families over the demo synthetic-fault scenario, attributes root cause, and
returns the alerts + a summary. Offline & deterministic; synthetic faults are flagged so they are
never presented as real incidents.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def anomalies() -> dict:
    from ml.anomaly import attribute_root_cause, detect_all
    from ml.anomaly.scenario import build_demo_scenario

    obs, events = build_demo_scenario()
    alerts = attribute_root_cause(detect_all(obs), events)

    by_type: dict[str, int] = {}
    by_root: dict[str, int] = {}
    for a in alerts:
        by_type[a.anomaly_type.value] = by_type.get(a.anomaly_type.value, 0) + 1
        by_root[a.root_cause_status.value] = by_root.get(a.root_cause_status.value, 0) + 1

    return {
        "mode": "live_shadow",
        "n_alerts": len(alerts),
        "synthetic_fault_count": sum(1 for a in alerts if a.is_synthetic_fault),
        "by_type": by_type,
        "by_root_cause": by_root,
        "note": (
            "데모 시나리오에 주입된 합성 결함(is_synthetic_fault=true)입니다 — 실제 인시던트가 "
            "아닙니다. 4개 탐지기(데이터품질·재고·예측잔차·프록시수요)가 오탐 없이 결함을 잡고, "
            "재고 급감은 이벤트로 근거 연결(explained_by_event)됩니다."
        ),
        "alerts": [
            {
                "anomaly_id": a.anomaly_id,
                "detector": a.detector,
                "anomaly_type": a.anomaly_type.value,
                "station_id": a.station_id,
                "zone_id": a.zone_id,
                "detected_at": a.detected_at.isoformat(),
                "score": a.score,
                "severity": a.severity,
                "root_cause_status": a.root_cause_status.value,
                "linked_event_ids": a.linked_event_ids,
                "evidence_article_ids": a.evidence_article_ids,
                "is_synthetic_fault": a.is_synthetic_fault,
            }
            for a in alerts
        ],
    }
