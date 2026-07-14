"""Root-cause attribution for anomalies (V1_Prompt §12).

Links an anomaly to source events when the zone/time overlaps, upgrading its status to
``explained_by_event`` with provenance (event ids + evidence article ids). Data-quality anomalies
stay ``likely_data_quality``; inventory/forecast anomalies with no event overlap stay
``inventory_dislocation`` / ``unexplained``. A true demand anomaly is never conflated with a live
proxy anomaly (§12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from contracts.v1.anomaly import AnomalyAlert
from contracts.v1.enums import AnomalyType, RootCauseStatus


@dataclass(frozen=True)
class EventLink:
    """Minimal event view for attribution (decouples anomaly from the event contract)."""

    event_id: str
    zone_id: str
    available_at: datetime
    article_ids: tuple[str, ...] = ()


_EVENT_ATTRIBUTABLE = {
    AnomalyType.INVENTORY,
    AnomalyType.FORECAST_RESIDUAL,
    AnomalyType.PROXY_DEMAND,
}


def attribute_root_cause(
    alerts: list[AnomalyAlert], events: list[EventLink]
) -> list[AnomalyAlert]:
    out: list[AnomalyAlert] = []
    for a in alerts:
        if a.anomaly_type not in _EVENT_ATTRIBUTABLE:
            out.append(a)  # data-quality keeps likely_data_quality
            continue
        linked = [
            e for e in events
            if e.zone_id == a.zone_id and e.available_at <= a.detected_at
        ]
        if linked:
            out.append(
                a.model_copy(
                    update={
                        "root_cause_status": RootCauseStatus.EXPLAINED_BY_EVENT,
                        "linked_event_ids": [e.event_id for e in linked],
                        "evidence_article_ids": sorted(
                            {aid for e in linked for aid in e.article_ids}
                        ),
                    }
                )
            )
        else:
            out.append(a)
    return out
