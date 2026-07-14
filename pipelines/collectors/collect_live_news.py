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

from config.backfill import BackfillConfig, GdeltConfig
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
                        "article_id": a.article_id, "title": a.title, "text": a.text,
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
    args = ap.parse_args()

    enabled = args.live or os.environ.get("ENABLE_GDELT_LIVE", "").lower() == "true"
    if not enabled:
        print("LIVE collection is opt-in. Re-run with --live or ENABLE_GDELT_LIVE=true.")
        print("Offline paths use data/fixtures/news_demo.jsonl (make v1-backfill-news).")
        return 0

    gcfg = GdeltConfig(enabled=True, start=args.start, end=args.end)
    provider = GdeltNewsProvider(
        gcfg.query, enabled=True, start=gcfg.start, end=gcfg.end,
        max_records=gcfg.max_records, source_lang=gcfg.source_lang,
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
    print(f"GDELT live: raw={rep.raw_article_count} candidate={rep.candidate_article_count} "
          f"accepted={rep.accepted_count} sources={rep.unique_source_count}")
    print(f"coverage gate passed: {gate.passed}  {gate.reasons or ''}")
    print(f"snapshot -> {snap.relative_to(_ROOT)} ({rep.accepted_count} articles)")
    print("Now point extraction/features at this snapshot for real event impact (V1-02+).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
