"""Why is the LLM-news arm net-negative? A trip-independent coverage/overlap diagnostic (V2-03).

Compares the structured permitted-event features (A1) against the LLM-extracted news-event
features (A2 increment) over a single month, purely from the two event indices — no trip data
needed. It quantifies the four reasons the news features add variance rather than signal:
sparsity, redundancy with the permitted feed, coarse (citywide) location, and how little genuinely
new information they carry.

    python -m scripts.llm_news_coverage_diag            # defaults to May 2026
    python -m scripts.llm_news_coverage_diag 2026-05
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

from ml.forecasting.borough_event_lift import build_event_index
from ml.forecasting.llm_value_borough import build_news_llm_index_precomputed

PERMITTED = Path("data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
NEWS = Path("data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
CLAUDE_EVENTS = Path("data/fixtures/news_live/claude_events_2026h1.jsonl")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    month = argv[0] if argv else "2026-05"

    permitted = build_event_index(PERMITTED)
    news, _ = build_news_llm_index_precomputed(NEWS, CLAUDE_EVENTS)

    p = {k for k in permitted if k[1].startswith(month)}
    n = {k for k in news if k[1].startswith(month)}
    overlap = p & n
    new_only = n - p

    hours = defaultdict(set)
    for b, h in n:
        hours[h].add(b)
    all5 = sum(1 for bs in hours.values() if len(bs) == 5)

    print(f"LLM-news vs permitted feature coverage — {month}")
    print("=" * 48)
    print(f"A1 permitted   : {len(p):5d} borough-hour cells with signal")
    print(f"A2 news (LLM)  : {len(n):5d} cells")
    print(f"  overlap      : {len(overlap):5d} cells already covered by permitted "
          f"({100 * len(overlap) / max(len(n), 1):.0f}% of news)")
    print(f"  genuinely new: {len(new_only):5d} cells the news adds beyond permitted")
    print(f"per-borough (permitted): {dict(Counter(k[0] for k in p))}")
    print(f"per-borough (news)     : {dict(Counter(k[0] for k in n))}")
    print(f"news hours hitting ALL 5 boroughs (flat time-dummies): {all5} of {len(hours)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
