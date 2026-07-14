"""Historical news backfill with a provider interface + coverage gate (V1_Prompt §7).

A ``NewsProvider`` yields raw article payloads. The deterministic ``FixtureNewsProvider`` is the
offline default; ``GdeltNewsProvider`` is a real-source stub that stays **disabled** without a live
key/network and reports a degraded state rather than fabricating data. Backfill deduplicates on
canonical url + normalised-title hash, filters by ontology + city, is restart-safe via a checkpoint
(re-running never adds duplicates), and persists a manifest.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from contracts.article import ArticleRecord
from contracts.enums import OperatingMode

from .base import sha256_hex

_WS = re.compile(r"\s+")


class ProviderUnavailable(RuntimeError):
    """Raised when a live provider is disabled/unreachable (degraded, not fabricated)."""


@runtime_checkable
class NewsProvider(Protocol):
    name: str

    def fetch(self) -> list[dict]:
        """Return raw article payload dicts (article_id,title,text,source,published_at,...)."""


class FixtureNewsProvider:
    """Deterministic offline provider: reads a JSONL fixture. Default backfill source."""

    name = "fixture"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self) -> list[dict]:
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out


class GdeltNewsProvider:
    """Real GDELT historical provider (V1_Prompt §7). Disabled offline — no fabricated data."""

    name = "gdelt"

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def fetch(self) -> list[dict]:
        if not self.enabled:
            raise ProviderUnavailable(
                "GDELT live fetch disabled (no key/network). Use FixtureNewsProvider offline; "
                "real-news coverage stays BLOCKED_DATA until the live path is available (§7)."
            )
        raise ProviderUnavailable("GDELT live client not implemented on the required offline path")


def title_hash(title: str) -> str:
    return sha256_hex(_WS.sub(" ", title.strip().lower()).encode("utf-8"))


def _matches(text: str, terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


@dataclass
class BackfillReport:
    provider: str
    raw_count: int
    candidate_count: int  # after ontology + city filter
    accepted_count: int
    excluded: dict[str, int] = field(default_factory=dict)
    unique_sources: int = 0
    source_distribution: dict[str, int] = field(default_factory=dict)
    manifest_path: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None


@dataclass
class BackfillResult:
    articles: list[ArticleRecord]
    report: BackfillReport


def _load_checkpoint(path: Path) -> set[str]:
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")).get("seen", []))
    return set()


def _save_checkpoint(path: Path, seen: set[str], report: BackfillReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"seen": sorted(seen), "accepted": report.accepted_count}, indent=2),
        encoding="utf-8",
    )


def backfill_news(
    provider: NewsProvider,
    config,
    checkpoint_path: str | Path | None = None,
    mode: OperatingMode = OperatingMode.HISTORICAL_REPLAY,
) -> BackfillResult:
    """Fetch → filter → dedup (restart-safe) → parse. Idempotent across re-runs (§7)."""
    ckpt = Path(checkpoint_path) if checkpoint_path else Path(config.checkpoint_dir) / "news.json"
    seen = _load_checkpoint(ckpt)

    try:
        raw = provider.fetch()
        degraded, reason = False, None
    except ProviderUnavailable as e:
        raw, degraded, reason = [], True, str(e)

    excluded: dict[str, int] = {}
    candidates: list[dict] = []
    for payload in raw:
        blob = f"{payload.get('title', '')} {payload.get('text', '')}"
        if config.require_ontology_match and not _matches(blob, config.ontology_terms):
            excluded["off_ontology"] = excluded.get("off_ontology", 0) + 1
            continue
        if config.require_city_match and not _matches(blob, config.city_terms):
            excluded["off_area"] = excluded.get("off_area", 0) + 1
            continue
        candidates.append(payload)

    accepted: list[ArticleRecord] = []
    sources: dict[str, int] = {}
    for payload in candidates:
        uh = payload.get("url_hash") or sha256_hex(str(payload.get("article_id", "")).encode())
        th = title_hash(payload.get("title", ""))
        key = f"u:{uh}"
        keyt = f"t:{th}"
        if key in seen or keyt in seen:
            excluded["duplicate"] = excluded.get("duplicate", 0) + 1
            continue
        # Validate timestamps + schema via the contract.
        data = dict(payload)
        data.setdefault("mode", mode.value)
        data.setdefault("raw_payload_path", str(getattr(provider, "path", provider.name)))
        for f in ("published_at", "first_seen_at"):
            datetime.fromisoformat(data[f])  # loud failure on bad timestamps
        rec = ArticleRecord(**data)
        accepted.append(rec)
        seen.add(key)
        seen.add(keyt)
        sources[rec.source] = sources.get(rec.source, 0) + 1

    accepted.sort(key=lambda a: a.available_at)  # type: ignore[arg-type,return-value]
    report = BackfillReport(
        provider=provider.name,
        raw_count=len(raw),
        candidate_count=len(candidates),
        accepted_count=len(accepted),
        excluded=excluded,
        unique_sources=len(sources),
        source_distribution=sources,
        manifest_path=str(ckpt),
        degraded=degraded,
        degraded_reason=reason,
    )
    _save_checkpoint(ckpt, seen, report)
    return BackfillResult(articles=accepted, report=report)
