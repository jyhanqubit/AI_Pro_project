"""Opt-in LIVE news collection from GDELT (V1_Prompt §7).

Collects real Jersey City / Hoboken mobility news from GDELT's free DOC 2.0 API, filters by
ontology + city, and **snapshots the accepted articles to a versioned fixture** so the rest of the
pipeline (extraction, features, forecasting) can run deterministically & offline afterwards.

This touches the public internet, so it is OPT-IN and never runs in Demo/tests:

    ENABLE_GDELT_LIVE=true python -m pipelines.collectors.collect_live_news
    # or: python -m pipelines.collectors.collect_live_news --live

Without the flag it refuses (no fabricated data) and points at the fixture path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from config.backfill import GDELT_QUERY_PRESETS, BackfillConfig, GdeltConfig
from pipelines.collectors.backfill import GdeltNewsProvider, backfill_news
from pipelines.collectors.coverage import coverage_gate, coverage_report

_ROOT = Path(__file__).resolve().parents[2]
_SNAP_DIR = _ROOT / "data" / "fixtures" / "news_live"


def _snapshot(articles, stamp: str) -> Path:
    _SNAP_DIR.mkdir(parents=True, exist_ok=True)
    out = _SNAP_DIR / f"news_gdelt_{stamp}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for a in articles:
            f.write(
                json.dumps(
                    {
                        "article_id": a.article_id,
                        "title": a.title,
                        "text": a.text,
                        "source": a.source,
                        "published_at": a.published_at.isoformat(),
                        "first_seen_at": a.first_seen_at.isoformat(),
                        "url_hash": a.url_hash,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="enable the live GDELT fetch (opt-in)")
    ap.add_argument("--start", default=None, help="YYYYMMDDHHMMSS UTC window start")
    ap.add_argument("--end", default=None, help="YYYYMMDDHHMMSS UTC window end")
    ap.add_argument("--stamp", default="latest", help="snapshot filename stamp (no clock in code)")
    ap.add_argument(
        "--region",
        choices=sorted(GDELT_QUERY_PRESETS),
        default="jc",
        help="query preset for the served area (jc = Jersey City/Hoboken demo, nyc = NYC core). "
        "Pair 'nyc' with an NYC trip window + the NYC gazetteer. A --query override wins.",
    )
    ap.add_argument(
        "--query",
        default=None,
        help="override the GDELT DOC query entirely (wins over --region); target your trip data's "
        "region/topics.",
    )
    ap.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="max GDELT records to request (raise for a real backfill to clear the coverage gate; "
        "GDELT caps a single request at 250)",
    )
    ap.add_argument(
        "--retries",
        type=int,
        default=6,
        help="GDELT fetch attempts before giving up (429s back off exponentially; default 6)",
    )
    ap.add_argument(
        "--backoff",
        type=float,
        default=10.0,
        help="base backoff seconds between GDELT retries (default 10; raise if 429s persist)",
    )
    args = ap.parse_args()

    enabled = args.live or os.environ.get("ENABLE_GDELT_LIVE", "").lower() == "true"
    if not enabled:
        print("LIVE collection is opt-in. Re-run with --live or ENABLE_GDELT_LIVE=true.")
        print("Offline paths use data/fixtures/news_demo.jsonl (make v1-backfill-news).")
        return 0

    # A zero-width or reversed window makes GDELT return an error page (looks like a JSON/429
    # failure). Fail fast with a clear message instead.
    if args.start and args.end and args.start >= args.end:
        print(f"invalid window: --start {args.start} must be BEFORE --end {args.end}")
        return 1

    query = args.query or GDELT_QUERY_PRESETS[args.region]
    gcfg = GdeltConfig(
        enabled=True,
        start=args.start,
        end=args.end,
        query=query,
        max_records=args.max_records or GdeltConfig.max_records,
    )
    provider = GdeltNewsProvider(
        gcfg.query,
        enabled=True,
        start=gcfg.start,
        end=gcfg.end,
        max_records=gcfg.max_records,
        source_lang=gcfg.source_lang,
        retries=args.retries,
        backoff_s=args.backoff,
    )
    # GDELT DOC returns title only and already location/topic-matched the FULL text server-side, so
    # a local title-only re-filter would wrongly drop relevant items. Trust the GDELT query here.
    cfg = BackfillConfig(
        require_city_match=False,
        require_ontology_match=False,
        checkpoint_dir=str(_ROOT / "data" / "processed" / "backfill_live"),
    )
    res = backfill_news(provider, cfg)
    rep = coverage_report(res.report)
    gate = coverage_gate(rep, cfg)

    if res.report.degraded:
        print(f"GDELT degraded: {res.report.degraded_reason}")
        return 1

    snap = _snapshot(res.articles, args.stamp)
    print(
        f"GDELT live: raw={rep.raw_article_count} candidate={rep.candidate_article_count} "
        f"accepted={rep.accepted_count} sources={rep.unique_source_count}"
    )
    print(f"coverage gate passed: {gate.passed}  {gate.reasons or ''}")
    print(f"snapshot -> {snap.relative_to(_ROOT)} ({rep.accepted_count} articles)")

    # Accumulate into the persistent FAISS news vector store (grows across collection runs).
    _accumulate_vectorstore(res.articles)
    print("Now point extraction/features at this snapshot for real event impact (V1-02+).")
    return 0


def _accumulate_vectorstore(articles) -> None:
    """Upsert collected articles into the persistent FAISS store (idempotent). Optional extra."""
    try:
        from config.vectorstore import VectorStoreConfig
        from ml.vectorstore import NewsRecord, NewsVectorStore
        from ml.vectorstore.news_store import VectorStoreUnavailable
    except ImportError:
        print("[vector store skipped] install the [vectorstore] extra to accumulate news vectors.")
        return
    try:
        cfg = VectorStoreConfig()
        store = NewsVectorStore.load_or_new(cfg.store_dir, cfg)
        added = store.add(
            [
                NewsRecord(
                    article_id=a.article_id,
                    title=a.title,
                    source=a.source,
                    published_at=a.published_at.isoformat(),
                    url_hash=a.url_hash,
                )
                for a in articles
            ]
        )
        store.save(cfg.store_dir)
        print(f"vector store: +{added} new (total {len(store)}) -> {cfg.store_dir}")
    except VectorStoreUnavailable as e:
        print(f"[vector store skipped] {e}")


if __name__ == "__main__":
    sys.exit(main())
