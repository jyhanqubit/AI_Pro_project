"""Event extraction demo: ``python -m pipelines.events.demo``.

Extracts events from the demo news fixture using the deterministic mock provider.
Backs the ``make extract-events-demo`` target (CLAUDE.md section 19).
"""

from __future__ import annotations

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events


def main() -> None:
    print("ShockFlow AI - LLM event extraction (mock provider)\n")

    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, meta = extract_events(articles, build_provider("mock"))

    print(f"prompt_version={meta.prompt_version}")
    print(
        f"articles={meta.articles} candidates={meta.candidates} "
        f"accepted={meta.accepted} quarantined={meta.quarantined} "
        f"rejected={meta.rejected} deduped={meta.deduped} errors={len(meta.errors)}\n"
    )
    for ev in events:
        span = ev.evidence_spans[0].text if ev.evidence_spans else "(none)"
        print(f"[{ev.status}] {ev.event_type} conf={ev.confidence:.2f} sev={ev.severity:.2f}")
        print(f"    title   : {ev.event_title}")
        print(f"    demand  : {ev.demand_effect}  capacity: {ev.capacity_effect}")
        print(f"    evidence: {span!r}")
        print(f"    sources : {ev.source_article_ids}")

    print("\nDone. Deterministic + offline; evidence spans grounded in article text.")


if __name__ == "__main__":
    main()
