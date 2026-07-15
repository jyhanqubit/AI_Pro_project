"""Graph upsert demo: ``python -m pipelines.graph.demo [--backend memory|neo4j|auto]``.

Collects the news fixture, extracts events (mock), upserts them into the selected graph store, and
prints node/edge counts and idempotency. ``--backend memory`` (default) is offline and backs
``make graph-upsert-demo``; ``--backend neo4j`` writes to a live Neo4j (``[graph]`` extra +
``docker compose up neo4j`` + credentials) and backs ``make graph-upsert-neo4j``. Re-running the
upsert must not change the logical counts (idempotency), on either backend. The provenance audit and
per-zone view are printed only on the in-memory backend (which exposes them).
"""

from __future__ import annotations

import argparse

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.graph import build_graph_store, upsert_events
from pipelines.graph.store import InMemoryGraphStore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipelines.graph.demo")
    ap.add_argument(
        "--backend",
        choices=("memory", "neo4j", "auto"),
        default="memory",
        help="graph backend (memory = offline in-memory; neo4j = live server via [graph] extra)",
    )
    args = ap.parse_args(argv)

    store = build_graph_store(args.backend)
    print(f"ShockFlow AI - event graph upsert (backend: {type(store).__name__})\n")

    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))

    _, meta = upsert_events(events, articles, store=store)
    print(f"events={meta.events}  nodes={meta.stats.total_nodes}  edges={meta.stats.total_edges}")
    print("nodes by label :", dict(sorted(meta.stats.nodes_by_label.items())))
    print("edges by type  :", dict(sorted(meta.stats.edges_by_type.items())))

    # Idempotency: replay the same events; logical counts must not grow.
    before = store.stats().total_nodes
    upsert_events(events, articles, store=store)
    after = store.stats().total_nodes
    print(f"\nreplay idempotency: nodes {before} -> {after} (unchanged: {before == after})")

    # Provenance audit + per-zone view are exposed by the in-memory backend.
    if isinstance(store, InMemoryGraphStore):
        audit = store.audit()
        print(
            f"audit clean: {audit.clean}  orphans={len(audit.orphan_nodes)}  "
            f"events_without_provenance={len(audit.events_without_provenance)}"
        )
        print("\nzones affected by events (feeds Phase 05 features):")
        for zone, ev in sorted(store.zones_affected_by_events().items()):
            print(f"  {zone}: {sorted(ev)}")

    print("\nDone. Graph is idempotent and connects events to H3 zones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
