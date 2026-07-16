"""Persist an in-memory event graph to a portable node-link JSON file. CLAUDE.md §9, §15.

The export is a plain, inspectable snapshot (nodes with labels/props + typed edges) that a reviewer
can open directly, load into networkx, or bulk-import into Neo4j. It is written under
``data/processed/`` (a generated artifact, git-ignored) — never committed as a large blob.
"""

from __future__ import annotations

import json
from pathlib import Path

from .store import InMemoryGraphStore


def export_graph(store: InMemoryGraphStore, path: str | Path) -> Path:
    """Write ``store`` to ``path`` as node-link JSON and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    nodes = [
        {"label": label, "key": key, "props": dict(props)}
        for (label, key), props in sorted(store._nodes.items())
    ]
    edges = [
        {"from": [fl, fk], "rel": rel, "to": [tl, tk]}
        for (fl, fk, rel, tl, tk) in sorted(store._edges)
    ]
    stats = store.stats()
    payload = {
        "schema": "shockflow-event-graph/1",
        "nodes_by_label": dict(sorted(stats.nodes_by_label.items())),
        "edges_by_type": dict(sorted(stats.edges_by_type.items())),
        "total_nodes": stats.total_nodes,
        "total_edges": stats.total_edges,
        "nodes": nodes,
        "edges": edges,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
