"""Feature snapshot contract. CLAUDE.md sections 6.4 and 10.

Each snapshot must let a reviewer trace a numeric feature back to its source events,
so ``feature_version`` and ``source_event_ids`` travel with the numeric values.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field

from .common import ContractModel


class FeatureSnapshot(ContractModel):
    zone_id: str = Field(min_length=1, description="H3 zone id.")
    forecast_cutoff: AwareDatetime
    feature_version: str = Field(min_length=1)
    source_event_ids: list[str] = Field(default_factory=list)
    features: dict[str, float] = Field(
        default_factory=dict,
        description="Numeric graph/temporal feature values keyed by feature name.",
    )
    created_at: AwareDatetime
