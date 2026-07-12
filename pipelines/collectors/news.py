"""Demo news fixture collector. CLAUDE.md sections 7.2, 6.2, 5.2.

Reads a JSONL fixture into ``ArticleRecord`` objects, deduplicates on article_id and
url_hash, and returns them ordered strictly by ``available_at`` (not event start time).
Invalid timestamps fail loudly with a precise message.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from contracts.article import ArticleRecord
from contracts.enums import OperatingMode

from .base import CollectionMetadata, CollectionResult, Collector, sha256_hex

_TIMESTAMP_FIELDS = ("published_at", "first_seen_at", "available_at")


class NewsFixtureError(ValueError):
    """Raised when a news fixture line cannot be parsed (e.g. invalid timestamp)."""


class NewsFixtureCollector(Collector[ArticleRecord]):
    name = "news_fixture"

    def __init__(
        self,
        path: str | Path,
        *,
        mode: OperatingMode = OperatingMode.HISTORICAL_REPLAY,
    ) -> None:
        self.path = Path(path)
        self.mode = mode

    def _parse_line(self, line: str, line_no: int) -> ArticleRecord:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise NewsFixtureError(
                f"news fixture line {line_no}: invalid JSON ({exc.msg})"
            ) from exc

        article_id = payload.get("article_id", "<unknown>")
        for field in _TIMESTAMP_FIELDS:
            raw = payload.get(field)
            if raw is None:
                continue
            try:
                datetime.fromisoformat(raw)
            except (TypeError, ValueError) as exc:
                raise NewsFixtureError(
                    f"news fixture line {line_no} (article_id={article_id}): "
                    f"invalid timestamp for '{field}': {raw!r}"
                ) from exc

        payload.setdefault("mode", self.mode.value)
        payload.setdefault("raw_payload_path", str(self.path))
        try:
            return ArticleRecord(**payload)
        except ValidationError as exc:
            raise NewsFixtureError(
                f"news fixture line {line_no} (article_id={article_id}): "
                f"schema validation failed: {exc.error_count()} error(s)"
            ) from exc

    def collect(self) -> CollectionResult[ArticleRecord]:
        raw_bytes = self.path.read_bytes()
        seen_ids: set[str] = set()
        seen_hashes: set[str] = set()
        records: list[ArticleRecord] = []
        reasons: dict[str, int] = {}
        total = 0

        for line_no, line in enumerate(raw_bytes.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            total += 1
            record = self._parse_line(line, line_no)
            if record.article_id in seen_ids or record.url_hash in seen_hashes:
                reasons["duplicate_article"] = reasons.get("duplicate_article", 0) + 1
                continue
            seen_ids.add(record.article_id)
            seen_hashes.add(record.url_hash)
            records.append(record)

        # Replay order is strictly by availability (section 7.2 / 5.2).
        records.sort(key=lambda a: a.available_at)  # type: ignore[arg-type,return-value]

        metadata = CollectionMetadata(
            collector=self.name,
            mode=self.mode,
            source=self.path.name,
            total_rows=total,
            accepted_rows=len(records),
            excluded_rows=sum(reasons.values()),
            exclusion_reasons=reasons,
            payload_hash=sha256_hex(raw_bytes),
            raw_payload_path=str(self.path),
        )
        return CollectionResult(records=records, metadata=metadata)

    def available_at_cutoff(
        self, records: list[ArticleRecord], cutoff: datetime
    ) -> list[ArticleRecord]:
        """Articles usable at a forecast cutoff: available_at <= cutoff (section 5.2)."""
        return [a for a in records if a.available_at is not None and a.available_at <= cutoff]
