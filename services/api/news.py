"""News vector-search + clustering for the API/UI (V1 — accumulating news).

Lazily builds a FAISS ``NewsVectorStore`` from the bundled news corpus (offline, deterministic) and
serves semantic search + same-event clusters. torch is not needed; faiss is the ``[vectorstore]``
extra — if absent the endpoints return an explicit degraded error, never fabricated results.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CORPUS = _ROOT / "data" / "fixtures" / "news_corpus.jsonl"


class NewsSearchUnavailable(RuntimeError):
    """Raised when the [vectorstore] extra (faiss) is not installed."""


@lru_cache(maxsize=1)
def _store():
    try:
        from ml.vectorstore import NewsRecord, NewsVectorStore
        from ml.vectorstore.news_store import VectorStoreUnavailable
    except ImportError as e:
        raise NewsSearchUnavailable(str(e)) from e
    try:
        store = NewsVectorStore()
    except VectorStoreUnavailable as e:
        raise NewsSearchUnavailable(str(e)) from e
    recs = []
    for line in _CORPUS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        a = json.loads(line)
        recs.append(
            NewsRecord(
                article_id=a["article_id"], title=a["title"], source=a.get("source", ""),
                published_at=a.get("published_at", ""), url_hash=a.get("url_hash", ""),
            )
        )
    store.add(recs)
    return store


def search(query: str, k: int = 5) -> dict:
    store = _store()
    hits = store.search(query, k=k)
    return {
        "query": query,
        "n_indexed": len(store),
        "embedder": "lexical-charhash-256 (offline, deterministic)",
        "results": [
            {
                "article_id": r.article_id, "title": r.title, "source": r.source,
                "published_at": r.published_at, "score": round(score, 4),
            }
            for r, score in hits
        ],
    }


def clusters(threshold: float = 0.3) -> dict:
    from ml.vectorstore.cluster import cluster_news

    store = _store()
    cl = cluster_news(store, threshold=threshold)
    return {
        "n_indexed": len(store),
        "threshold": threshold,
        "n_clusters": len(cl),
        "clusters": [
            {
                "cluster_id": c.cluster_id, "size": c.size,
                "representative_title": c.representative_title, "article_ids": c.article_ids,
            }
            for c in cl
        ],
    }
