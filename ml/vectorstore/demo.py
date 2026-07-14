"""FAISS news vector-store demo (offline).

    python -m ml.vectorstore.demo

Builds a store from the demo news fixture, runs a semantic search, flags near-duplicates, and shows
persistence + accumulation (save -> reload -> re-add is idempotent).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from config.vectorstore import VectorStoreConfig
from ml.vectorstore import NewsRecord, NewsVectorStore
from ml.vectorstore.news_store import VectorStoreUnavailable

_ROOT = Path(__file__).resolve().parents[2]
_NEWS = _ROOT / "data" / "fixtures" / "news_demo.jsonl"
_STORE = _ROOT / "data" / "processed" / "vectorstore" / "news_demo"


def _records() -> list[NewsRecord]:
    out: list[NewsRecord] = []
    for line in _NEWS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        a = json.loads(line)
        out.append(
            NewsRecord(
                article_id=a["article_id"], title=a["title"], source=a.get("source", ""),
                published_at=a.get("published_at", ""), url_hash=a.get("url_hash", ""),
            )
        )
    return out


def main() -> int:
    try:
        store = NewsVectorStore.load_or_new(_STORE, VectorStoreConfig(store_dir=str(_STORE)))
    except VectorStoreUnavailable as e:
        print(f"[vectorstore extra not installed] {e}")
        return 0

    recs = _records()
    added = store.add(recs)
    print(f"added {added} articles (store now holds {len(store)})")

    print("\nsemantic search: 'PATH train suspended near Hoboken'")
    for r, score in store.search("PATH train suspended near Hoboken", k=3):
        print(f"  {score:.3f}  {r.title[:60]}")

    dups = store.near_duplicates()
    print(f"\nnear-duplicate pairs (cosine >= {store.cfg.dedup_threshold}): {len(dups)}")
    for a, b, s in dups[:5]:
        print(f"  {a} ~ {b}  ({s:.3f})")

    store.save(_STORE)
    reloaded = NewsVectorStore.load(_STORE)
    re_added = reloaded.add(recs)  # accumulation is idempotent
    print(f"\npersist -> reload: {len(reloaded)} articles; "
          f"re-add duplicates added {re_added} (0 = idempotent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
