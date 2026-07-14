"""Anomaly + root-cause contract (V1_Prompt §12).

Synthetic faults injected for testing MUST carry ``is_synthetic_fault=true`` so they can never be
mistaken for a real incident. Root-cause explanations trace to source event/article evidence.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field

from contracts.common import ContractModel

from .enums import AnomalyType, ClaimState, OperatingModeV1, RootCauseStatus


class AnomalyAlert(ContractModel):
    anomaly_id: str = Field(min_length=1)
    detector: str = Field(min_length=1, description="Detector name/version that fired.")
    anomaly_type: AnomalyType
    zone_id: str | None = None
    station_id: str | None = None
    detected_at: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    score: float = Field(description="Detector score (e.g. robust z-score).")
    severity: float = Field(ge=0.0, le=1.0)

    root_cause_status: RootCauseStatus
    linked_event_ids: list[str] = Field(default_factory=list)
    evidence_article_ids: list[str] = Field(default_factory=list)

    is_synthetic_fault: bool = False
    claim_state: ClaimState
    mode: OperatingModeV1
