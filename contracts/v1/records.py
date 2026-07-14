"""Article/event ingestion contracts for V1 news backfill & extraction (V1_Prompt §7, §8).

These carry the provenance and availability fields the leakage rules depend on: an article is
usable only when ``available_at <= cutoff`` (CLAUDE.md §5.2), where
``available_at = max(published_at, first_seen_at)``.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from contracts.common import ContractModel
from contracts.enums import EffectDirection, EventType, ExtractionStatus

from .enums import OperatingModeV1


class ArticleRecord(ContractModel):
    """A historical or live news article as persisted after backfill (V1_Prompt §7)."""

    article_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(default="", description="Permitted snippet/description; may be empty.")
    source: str = Field(min_length=1)
    url_hash: str = Field(min_length=1, description="Canonical-URL hash for dedup.")
    title_hash: str = Field(min_length=1, description="Normalised-title hash for near-dup dedup.")
    published_at: AwareDatetime
    first_seen_at: AwareDatetime
    available_at: AwareDatetime
    fetched_at: AwareDatetime
    ingested_at: AwareDatetime
    raw_payload_path: str = Field(min_length=1)
    mode: OperatingModeV1

    @model_validator(mode="after")
    def _availability(self) -> ArticleRecord:
        expected = max(self.published_at, self.first_seen_at)
        if self.available_at < expected:
            raise ValueError(
                "available_at must be >= max(published_at, first_seen_at) (CLAUDE.md §5.2)"
            )
        return self


class EventRecordV1(ContractModel):
    """Structured event extracted from article metadata (V1_Prompt §8).

    The extractor emits severity/confidence/direction/mechanism + provenance only — never a
    numeric demand percentage (CLAUDE.md §8, invariant 3/4).
    """

    event_id: str = Field(min_length=1)
    source_article_ids: list[str] = Field(min_length=1)
    event_type: EventType
    event_title: str = Field(min_length=1)
    event_summary: str = Field(default="")
    published_at: AwareDatetime
    first_seen_at: AwareDatetime
    available_at: AwareDatetime
    event_start_at: AwareDatetime | None = None
    event_end_at: AwareDatetime | None = None
    demand_effect: EffectDirection
    severity: float = Field(ge=0.0, le=1.0, description="Bounded ordinal prior, not an effect.")
    confidence: float = Field(ge=0.0, le=1.0)
    mechanism: str = Field(default="")
    evidence_spans: list[str] = Field(min_length=1, description="Grounded; non-empty (§6.3).")
    extraction_model: str = Field(min_length=1)
    extraction_prompt_version: str = Field(min_length=1)
    status: ExtractionStatus
    feature_config_hash: str = Field(default="")
    mode: OperatingModeV1

    @model_validator(mode="after")
    def _availability(self) -> EventRecordV1:
        if self.available_at < max(self.published_at, self.first_seen_at):
            raise ValueError("available_at must be >= max(published_at, first_seen_at)")
        if self.event_end_at and self.event_start_at and self.event_end_at < self.event_start_at:
            raise ValueError("event_end_at must be >= event_start_at")
        return self
