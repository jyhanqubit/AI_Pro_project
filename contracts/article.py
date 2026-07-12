"""Article record contract. CLAUDE.md sections 6.2 and 5.2.

Enforces the availability rule: ``available_at = max(published_at, first_seen_at)``.
A past event start never makes an article available before it was published/observed.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from .common import ContractModel
from .enums import OperatingMode


class ArticleRecord(ContractModel):
    article_id: str = Field(min_length=1)
    title: str
    text: str = Field(description="Full text or permitted snippet only.")
    source: str = Field(min_length=1)
    published_at: AwareDatetime
    first_seen_at: AwareDatetime
    available_at: AwareDatetime | None = Field(
        default=None,
        description="Computed as max(published_at, first_seen_at) when omitted.",
    )
    url_hash: str = Field(min_length=1)
    mode: OperatingMode
    raw_payload_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def _enforce_availability_rule(self) -> ArticleRecord:
        expected = max(self.published_at, self.first_seen_at)
        if self.available_at is None:
            self.available_at = expected
        elif self.available_at != expected:
            raise ValueError(
                "available_at must equal max(published_at, first_seen_at); "
                f"got {self.available_at.isoformat()}, expected {expected.isoformat()}"
            )
        return self
