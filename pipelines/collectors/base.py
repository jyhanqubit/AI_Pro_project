"""Common collector interface and result metadata. CLAUDE.md sections 7 and 6.1.

Every collector returns records plus a ``CollectionMetadata`` that records provenance and
exclusion statistics. Bad records are never silently discarded; they are counted by reason.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import AwareDatetime, Field

from contracts.common import ContractModel
from contracts.enums import OperatingMode

T = TypeVar("T")


class CollectionMetadata(ContractModel):
    """Provenance and quality statistics for one collection run (section 7.1)."""

    collector: str = Field(min_length=1)
    mode: OperatingMode
    source: str = Field(min_length=1, description="Source file name or URL.")
    collected_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    total_rows: int = Field(default=0, ge=0)
    accepted_rows: int = Field(default=0, ge=0)
    excluded_rows: int = Field(default=0, ge=0)
    exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    schema_hash: str | None = None
    payload_hash: str | None = None
    raw_payload_path: str | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass
class CollectionResult(Generic[T]):
    """Records plus the metadata describing how they were collected."""

    records: list[T]
    metadata: CollectionMetadata


class Collector(ABC, Generic[T]):
    """Common collector interface (section 7.3)."""

    name: str

    @abstractmethod
    def collect(self) -> CollectionResult[T]:
        """Collect records and return them with collection metadata."""
        raise NotImplementedError


def sha256_hex(data: bytes) -> str:
    """Stable content hash for payloads and schemas."""
    return hashlib.sha256(data).hexdigest()


def schema_hash_from_headers(headers: list[str]) -> str:
    """Order-independent hash of a tabular source's column names."""
    normalized = sorted(h.strip().lower() for h in headers)
    return sha256_hex("\n".join(normalized).encode("utf-8"))
