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
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
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


_GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"


def _is_429(err: Exception) -> bool:
    """True for an HTTP 429 (GDELT rate limit)."""
    return isinstance(err, urllib.error.HTTPError) and err.code == 429


class GdeltNewsProvider:
    """Real GDELT DOC 2.0 news provider (V1_Prompt §7).

    Hits GDELT's free, key-less DOC API when ``enabled`` (opt-in — live network). Disabled by
    default so Demo/tests stay offline (unit/integration tests must not touch the internet). GDELT
    DOC returns title + metadata only (no full body); ``text`` is left empty (title-only snippet),
    never fabricated. ``seendate`` is GDELT's first-seen time (UTC); we use it for both
    ``published_at`` and ``first_seen_at`` (documented approximation).
    """

    name = "gdelt"

    def __init__(
        self,
        query: str,
        *,
        enabled: bool = False,
        start: str | None = None,  # "YYYYMMDDHHMMSS" (UTC)
        end: str | None = None,
        max_records: int = 75,
        source_lang: str = "english",
        timeout: float = 30.0,
        retries: int = 6,
        backoff_s: float = 10.0,
    ) -> None:
        self.query = query
        self.enabled = enabled
        self.start = start
        self.end = end
        self.max_records = max_records
        self.source_lang = source_lang
        self.timeout = timeout
        self.retries = retries
        self.backoff_s = backoff_s

    def _url(self) -> str:
        params = {
            "query": self.query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(self.max_records),
            "sort": "datedesc",
            "sourcelang": self.source_lang,
        }
        if self.start:
            params["startdatetime"] = self.start
        if self.end:
            params["enddatetime"] = self.end
        return f"{_GDELT_DOC}?{urllib.parse.urlencode(params)}"

    def fetch(self) -> list[dict]:
        if not self.enabled:
            raise ProviderUnavailable(
                "GDELT live fetch disabled by default (opt-in). Set enabled=True / "
                "ENABLE_GDELT_LIVE=true to collect real news; offline uses FixtureNewsProvider."
            )
        url = self._url()
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                headers = {"User-Agent": "ShockFlowAI/1.0 research"}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
                    raw = r.read().decode("utf-8", "replace")
                articles = json.loads(raw).get("articles", []) if raw.strip() else []
                return [self._to_payload(a) for a in articles if a.get("url") and a.get("title")]
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
                last = e
                if attempt < self.retries - 1:
                    wait = self._retry_wait(e, attempt)
                    reason = "HTTP 429 (rate limit)" if _is_429(e) else type(e).__name__
                    print(
                        f"[gdelt] {reason}; waiting {wait:.0f}s "
                        f"(attempt {attempt + 1}/{self.retries})",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
        raise ProviderUnavailable(
            f"GDELT fetch failed after {self.retries} attempts: {last}. If this is a 429, GDELT is "
            "rate-limiting your IP for a while — wait a few minutes and re-run (only the missing "
            "months refetch), slow down (--backoff 20 or the scripts' -NewsDelaySeconds 20+), or "
            "fetch fewer months at a time."
        )

    def _retry_wait(self, err: Exception, attempt: int) -> float:
        """Backoff seconds before the next attempt.

        GDELT rate-limits bursty querying with HTTP 429; honour its ``Retry-After`` header when
        present, else back off **exponentially** (429 needs a longer pause than a transient error).
        Other errors use the gentler linear backoff. Capped so a run never hangs for minutes.
        """
        if isinstance(err, urllib.error.HTTPError) and err.code == 429:
            retry_after = err.headers.get("Retry-After") if err.headers else None
            if retry_after and str(retry_after).strip().isdigit():
                return min(120.0, float(retry_after))
            return min(120.0, self.backoff_s * (2**attempt))  # 10, 20, 40, 80 …
        return self.backoff_s * (attempt + 1)  # linear for transient errors

    @staticmethod
    def _to_payload(a: dict) -> dict:
        seen = _parse_gdelt_date(a["seendate"])
        url = a["url"]
        return {
            "article_id": sha256_hex(url.encode())[:16],
            "title": a["title"],
            "text": "",  # GDELT DOC gives no body; title-only snippet (not fabricated)
            "source": a.get("domain", "gdelt"),
            "published_at": seen,
            "first_seen_at": seen,
            "url_hash": sha256_hex(url.encode()),
            "url": url,
        }


def _parse_gdelt_date(s: str) -> str:
    """'20260714T131500Z' -> ISO-8601 UTC string."""
    dt = datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return dt.isoformat()


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
        # Validate timestamps + schema via the contract (drop non-contract keys like raw 'url').
        data = {k: v for k, v in payload.items() if k != "url"}
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
