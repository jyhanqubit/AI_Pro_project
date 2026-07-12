"""Event extraction contract. CLAUDE.md sections 6.3, 4 (invariant 5), and 8.

Every ACCEPTED event must carry source provenance and non-empty evidence spans.
Rejected/quarantined extractions remain auditable and are not required to be complete.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from .common import ContractModel
from .enums import EffectDirection, EventType, ExtractionStatus


class Location(ContractModel):
    name: str = Field(min_length=1)
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lng: float | None = Field(default=None, ge=-180.0, le=180.0)
    h3_zone: str | None = None


class EvidenceSpan(ContractModel):
    """A span grounded in the source article text (CLAUDE.md section 8)."""

    article_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)


class EventExtraction(ContractModel):
    event_id: str = Field(min_length=1)
    source_article_ids: list[str] = Field(default_factory=list)
    event_type: EventType
    event_title: str = Field(min_length=1)
    event_summary: str
    published_at: AwareDatetime
    first_seen_at: AwareDatetime
    available_at: AwareDatetime | None = None
    event_start_at: AwareDatetime | None = None
    event_end_at: AwareDatetime | None = None
    locations: list[Location] = Field(default_factory=list)
    demand_effect: EffectDirection = EffectDirection.UNKNOWN
    capacity_effect: EffectDirection = EffectDirection.UNKNOWN
    severity: float = Field(
        ge=0.0, le=1.0, description="Ordinal/bounded prior, not a causal effect."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    extraction_model: str = Field(min_length=1)
    extraction_prompt_version: str = Field(min_length=1)
    status: ExtractionStatus

    @model_validator(mode="after")
    def _validate(self) -> EventExtraction:
        # Availability rule (section 5.2), consistent with ArticleRecord.
        expected = max(self.published_at, self.first_seen_at)
        if self.available_at is None:
            self.available_at = expected
        elif self.available_at != expected:
            raise ValueError("available_at must equal max(published_at, first_seen_at)")

        if (
            self.event_start_at is not None
            and self.event_end_at is not None
            and self.event_end_at < self.event_start_at
        ):
            raise ValueError("event_end_at must not be before event_start_at")

        # Accepted events require provenance and grounded evidence (invariant 5, section 8).
        if self.status is ExtractionStatus.ACCEPTED:
            if not self.source_article_ids:
                raise ValueError("accepted event requires non-empty source_article_ids")
            if not self.evidence_spans:
                raise ValueError("accepted event requires non-empty evidence_spans")
        return self
