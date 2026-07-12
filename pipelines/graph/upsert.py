"""Graph upsert orchestrator. CLAUDE.md section 9.

Applies constraints, translates events into graph ops, upserts them idempotently, and
returns run metadata. Auditing (orphans / missing provenance) is available on stores that
support it (the in-memory backend). Neo4j is optional; the default is offline.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.features import H3_RESOLUTION
from contracts.article import ArticleRecord
from contracts.event import EventExtraction

from .model import build_graph_ops
from .store import GraphStats, GraphStore, InMemoryGraphStore


@dataclass
class GraphUpsertMetadata:
    events: int
    nodes_written: int
    edges_written: int
    stats: GraphStats


def upsert_events(
    events: list[EventExtraction],
    articles: list[ArticleRecord],
    *,
    store: GraphStore | None = None,
    resolution: int = H3_RESOLUTION,
) -> tuple[GraphStore, GraphUpsertMetadata]:
    """Upsert events into a graph store (offline in-memory by default)."""
    store = store if store is not None else InMemoryGraphStore()
    articles_by_id = {a.article_id: a for a in articles}

    store.apply_constraints()
    ops = build_graph_ops(events, articles_by_id, resolution=resolution)
    store.upsert(ops)

    meta = GraphUpsertMetadata(
        events=len(events),
        nodes_written=len(ops.nodes),
        edges_written=len(ops.edges),
        stats=store.stats(),
    )
    return store, meta
