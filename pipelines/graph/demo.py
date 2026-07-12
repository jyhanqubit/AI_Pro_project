"""Graph upsert demo: ``python -m pipelines.graph.demo``.

Collects the news fixture, extracts events (mock), upserts them into the offline in-memory
graph, and prints node/edge counts, an audit, and the zones each event affects. Re-running
the upsert must not change the counts (idempotency). Backs ``make graph-upsert-demo``.
"""

from __future__ import annotations

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.graph import upsert_events
from pipelines.graph.store import InMemoryGraphStore


def main() -> None:
    print("ShockFlow AI - event graph upsert (offline in-memory)\n")

    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))

    store = InMemoryGraphStore()
    _, meta = upsert_events(events, articles, store=store)
    print(f"events={meta.events}  nodes={meta.stats.total_nodes}  edges={meta.stats.total_edges}")
    print("nodes by label :", dict(sorted(meta.stats.nodes_by_label.items())))
    print("edges by type  :", dict(sorted(meta.stats.edges_by_type.items())))

    # Idempotency: replay the same events; counts must not grow.
    before = store.stats().total_nodes
    upsert_events(events, articles, store=store)
    after = store.stats().total_nodes
    print(f"\nreplay idempotency: nodes {before} -> {after} (unchanged: {before == after})")

    audit = store.audit()
    print(
        f"audit clean: {audit.clean}  orphans={len(audit.orphan_nodes)}  "
        f"events_without_provenance={len(audit.events_without_provenance)}"
    )

    print("\nzones affected by events (feeds Phase 05 features):")
    for zone, ev in sorted(store.zones_affected_by_events().items()):
        print(f"  {zone}: {sorted(ev)}")

    print("\nDone. Graph is offline, idempotent, and connects events to H3 zones.")


if __name__ == "__main__":
    main()
