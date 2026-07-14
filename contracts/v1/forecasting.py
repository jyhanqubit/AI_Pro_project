"""Dual-inference forecast contracts (V1_Prompt §9, §10).

V1 replaces the demo heuristic with real M0/M1 model artifacts. Every serving forecast is a
*pair* (baseline M0 vs event-aware M1) plus a counterfactual M1-zero, all as-of the same cutoff,
and carries a ``ClaimState`` (measured once a label arrives, else pending).
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from contracts.common import ContractModel
from contracts.enums import TargetName

from .enums import ClaimState, OperatingModeV1


class ForecastPair(ContractModel):
    """M0 / M1 / M1-zero predictions for one zone-hour target (V1_Prompt §9)."""

    zone_id: str = Field(min_length=1)
    forecast_cutoff: AwareDatetime
    forecast_horizon: int = Field(gt=0)
    target_name: TargetName

    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    train_window_id: str = Field(min_length=1)
    seed: int

    m0_baseline: float = Field(description="Demand history + calendar baseline.")
    m1_event_aware: float = Field(description="M0 + LLM event + graph-spatial features.")
    m1_zero: float = Field(description="M1 with event features zeroed at the same cutoff.")

    p10: float | None = None
    p50: float | None = None
    p90: float | None = None

    source_event_ids: list[str] = Field(default_factory=list)
    claim_state: ClaimState
    mode: OperatingModeV1

    @property
    def event_delta(self) -> float:
        """Model-attributed event effect (not causal): M1 - M1-zero."""
        return self.m1_event_aware - self.m1_zero

    @model_validator(mode="after")
    def _validate(self) -> ForecastPair:
        if self.p10 is not None and self.p50 is not None and self.p90 is not None:
            if not (self.p10 <= self.p50 <= self.p90):
                raise ValueError("quantiles must satisfy p10 <= p50 <= p90")
        return self


class ScoredForecastPair(ContractModel):
    """A ForecastPair joined to its realised label once it arrives (V1_Prompt §9, §10).

    ``actual`` is null while ``claim_state == PENDING``; it is populated (and claim_state becomes
    MEASURED) only after the delayed Trip-History label is linked. GBFS inventory deltas are never
    used as the label (invariant 8).
    """

    pair: ForecastPair
    actual: float | None = None
    label_source: str | None = Field(
        default=None, description="e.g. 'trip_history'; null until a real label links."
    )
    scored_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _consistency(self) -> ScoredForecastPair:
        measured = self.pair.claim_state == ClaimState.MEASURED
        if measured and self.actual is None:
            raise ValueError("MEASURED pair requires a non-null actual label")
        if self.actual is not None and self.label_source is None:
            raise ValueError("actual label requires a label_source")
        return self
