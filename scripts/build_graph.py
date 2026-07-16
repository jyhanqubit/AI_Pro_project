"""Build the ShockFlow event graph from the data already in the repo. CLAUDE.md §9, §15.

Combines two real sources into one §9 graph and persists a portable snapshot:

* **News** (``data/fixtures/news_live/*.jsonl``) -> mock extraction -> events. Provenance-rich
  (Article -> Event -> Source), spatially sparse (few articles name a gazetteer place).
* **NYC permitted events** (``data/fixtures/nyc_permitted_events_filtered.jsonl.gz``) -> official
  planned-event records grounded at their borough centroid. Spatially rich (Event -> Place ->
  H3Zone) across five boroughs.

Usage::

    python -m scripts.build_graph                      # memory backend, default caps, JSON export
    python -m scripts.build_graph --permitted-limit 0  # skip permitted events (news only)
    python -m scripts.build_graph --backend neo4j      # live Neo4j ([graph] extra + a server)

Re-running is idempotent (logical counts do not grow). ``--backend neo4j`` writes to a live server;
``memory`` (default) is offline and also writes a JSON snapshot under ``data/processed/graph/``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.graph import build_graph_store, upsert_events
from pipelines.graph.export import export_graph
from pipelines.graph.permitted_events import load_permitted_as_events
from pipelines.graph.store import InMemoryGraphStore

_NEWS_DIR = Path("data/fixtures/news_live")
_PERMITTED = Path("data/fixtures/nyc_permitted_events_filtered.jsonl.gz")
_DEFAULT_OUT = Path("data/processed/graph/event_graph.json")


def _load_news_articles() -> list:
    """Collect every readable news_live JSONL (falls back to the demo fixture if none)."""
    articles: list = []
    files = sorted(_NEWS_DIR.glob("*.jsonl")) if _NEWS_DIR.exists() else []
    for f in files:
        try:
            articles.extend(NewsFixtureCollector(f).collect().records)
        except (UnicodeDecodeError, ValueError) as exc:
            print(f"  skip {f.name}: {str(exc)[:60]}")
    if not articles:
        articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    return articles


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scripts.build_graph")
    ap.add_argument("--backend", choices=("memory", "neo4j", "auto"), default="memory")
    ap.add_argument(
        "--permitted-limit",
        type=int,
        default=3000,
        help="max permitted-event records to ingest (0 = skip; -1 = all ~63k)",
    )
    ap.add_argument(
        "--out", type=Path, default=_DEFAULT_OUT, help="JSON snapshot path (memory backend only)"
    )
    args = ap.parse_args(argv)

    store = build_graph_store(args.backend)
    print(f"ShockFlow AI — build event graph (backend: {type(store).__name__})\n")

    # 1) News -> events (mock extractor; deterministic, offline).
    print("news source:")
    articles = _load_news_articles()
    news_events, nmeta = extract_events(articles, build_provider("mock"))
    print(f"  articles={len(articles)}  events={nmeta.accepted}")
    events = list(news_events)
    articles_by_id = {a.article_id: a for a in articles}

    # 2) NYC permitted events -> events grounded at borough centroids.
    if args.permitted_limit != 0 and _PERMITTED.exists():
        limit = None if args.permitted_limit < 0 else args.permitted_limit
        pevents, particles = load_permitted_as_events(_PERMITTED, limit=limit)
        print(f"permitted events: records={len(pevents)} (limit={args.permitted_limit})")
        events.extend(pevents)
        articles_by_id.update(particles)
    else:
        print("permitted events: skipped")

    # 3) Upsert everything into the graph.
    _, gmeta = upsert_events(events, list(articles_by_id.values()), store=store)
    print(f"\nGRAPH  nodes={gmeta.stats.total_nodes}  edges={gmeta.stats.total_edges}")
    print("  nodes by label:", dict(sorted(gmeta.stats.nodes_by_label.items())))
    print("  edges by type :", dict(sorted(gmeta.stats.edges_by_type.items())))

    # 4) Idempotency check — re-applying must not grow logical counts (§9).
    before = store.stats().total_nodes
    upsert_events(events, list(articles_by_id.values()), store=store)
    after = store.stats().total_nodes
    print(f"  replay idempotency: nodes {before} -> {after} (unchanged: {before == after})")

    # 5) Audit + persist (in-memory backend exposes these).
    if isinstance(store, InMemoryGraphStore):
        audit = store.audit()
        print(
            f"  audit clean: {audit.clean}  orphans={len(audit.orphan_nodes)}  "
            f"events_without_provenance={len(audit.events_without_provenance)}"
        )
        out = export_graph(store, args.out)
        print(f"\nsnapshot written: {out}  ({out.stat().st_size / 1024:.0f} KB)")
    else:
        print("\n(neo4j backend: graph written to the live server; no local JSON snapshot)")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
