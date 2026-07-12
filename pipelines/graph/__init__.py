"""Event graph upsert (CLAUDE.md section 9). Offline in-memory by default; Neo4j optional."""

from __future__ import annotations

from .model import GraphOps, Node, build_graph_ops
from .store import AuditReport, GraphStats, GraphStore, InMemoryGraphStore
from .upsert import GraphUpsertMetadata, upsert_events

__all__ = [
    "build_graph_ops",
    "GraphOps",
    "Node",
    "GraphStore",
    "InMemoryGraphStore",
    "GraphStats",
    "AuditReport",
    "upsert_events",
    "GraphUpsertMetadata",
]
