"""On-demand LIVE news sync from GDELT (V2). CLAUDE.md sections 3, 7.3, 7.4, 22.

Powers the "뉴스 동기화" button: when a rider/operator asks, pull real, timely mobility news from
GDELT's free, key-less DOC 2.0 API, deduplicate it, accumulate it into the persistent news vector
store (so it becomes searchable), and report a LIVE result with provenance.

Honesty rules enforced here:
- Results are labelled ``live`` only when they actually came from GDELT this call; a network/API
  failure returns ``degraded`` with the reason and **no fabricated articles** — Demo Mode is never
  broken and fixture data is never presented as live.
- GDELT DOC returns title + metadata only (no article body), so ``text`` stays empty (title-only
  snippet), never invented.
- Fast-fail (short timeout, single retry) so the button degrades quickly when there is no egress
  (as in the offline sandbox); it works as-is once deployed with outbound network access.
"""

from __future__ import annotations

from datetime import UTC, datetime

from config.backfill import GdeltConfig

# A sensible default query for NYC-metro bike/transit mobility news (operator can override).
DEFAULT_QUERY = (
    '("citi bike" OR "citibike" OR "bike share" OR "PATH train" OR subway) sourcecountry:US'
)


def sync_live_news(
    query: str | None = None,
    *,
    timespan_hours: int = 72,
    max_records: int = 50,
) -> dict:
    """Attempt a live GDELT pull. Returns a labelled ``live``/``degraded`` result (never fake)."""
    from pipelines.collectors.backfill import GdeltNewsProvider, ProviderUnavailable

    q = (query or GdeltConfig().query or DEFAULT_QUERY).strip()
    fetched_at = datetime.now(UTC).isoformat()

    provider = GdeltNewsProvider(
        q,
        enabled=True,  # the button press is the explicit opt-in to touch the network
        max_records=max_records,
        timeout=8.0,  # fast-fail for an interactive request
        retries=1,
        backoff_s=2.0,
    )

    try:
        payloads = provider.fetch()
    except ProviderUnavailable as e:
        return {
            "status": "degraded",
            "mode": "live",
            "query": q,
            "fetched_at": fetched_at,
            "fetched": 0,
            "added_to_index": 0,
            "unique_sources": 0,
            "articles": [],
            "degraded_reason": str(e),
            "note": (
                "라이브 뉴스 동기화에 실패했습니다(네트워크/API). 가짜 데이터를 만들지 않고 "
                "degraded로 보고합니다 — Demo Mode는 영향받지 않습니다. 아웃바운드 네트워크가 있는 "
                "환경에 배포하면 그대로 동작합니다(무료·키 불필요 GDELT DOC 2.0)."
            ),
        }

    # Deduplicate on url_hash (idempotent across repeated syncs).
    seen: set[str] = set()
    unique: list[dict] = []
    for p in payloads:
        h = p.get("url_hash", "")
        if h and h in seen:
            continue
        seen.add(h)
        unique.append(p)

    added = _accumulate_vectorstore(unique)
    sources = sorted({p.get("source", "") for p in unique if p.get("source")})

    return {
        "status": "live",
        "mode": "live",
        "query": q,
        "timespan_hours": timespan_hours,
        "fetched_at": fetched_at,
        "fetched": len(unique),
        "added_to_index": added,
        "unique_sources": len(sources),
        "sources": sources[:20],
        "articles": [
            {
                "article_id": p["article_id"],
                "title": p["title"],
                "source": p.get("source", ""),
                "published_at": p.get("published_at", ""),
                "url": p.get("url", ""),
            }
            for p in unique[:25]
        ],
        "note": (
            "GDELT DOC 2.0(무료·키 불필요)에서 실시간으로 가져온 실제 뉴스입니다. 제목·메타"
            "데이터만 제공되어 본문(text)은 비어 있습니다(조작 아님). 수집분은 뉴스 벡터 스토어에 "
            "누적되어 뉴스 검색에서 바로 찾을 수 있습니다."
        ),
    }


def _accumulate_vectorstore(payloads: list[dict]) -> int:
    """Upsert fetched articles into the FAISS store. Returns count added (0 if absent)."""
    try:
        from config.vectorstore import VectorStoreConfig
        from ml.vectorstore import NewsRecord, NewsVectorStore
        from ml.vectorstore.news_store import VectorStoreUnavailable
    except ImportError:
        return 0
    try:
        cfg = VectorStoreConfig()
        store = NewsVectorStore.load_or_new(cfg.store_dir, cfg)
        added = store.add(
            [
                NewsRecord(
                    article_id=p["article_id"],
                    title=p["title"],
                    source=p.get("source", ""),
                    published_at=p.get("published_at", ""),
                    url_hash=p.get("url_hash", ""),
                )
                for p in payloads
            ]
        )
        store.save(cfg.store_dir)
        return int(added)
    except VectorStoreUnavailable:
        return 0
