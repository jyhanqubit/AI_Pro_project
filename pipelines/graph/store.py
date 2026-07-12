"""Graph store interface + offline in-memory backend. CLAUDE.md sections 9 and 3.

The in-memory store implements the same idempotent-upsert semantics as Neo4j so Demo Mode
and tests need no live database. Re-applying the same GraphOps never increases logical node
or edge counts (section 9). ``audit`` surfaces orphan nodes and events missing provenance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .model import GraphOps, Node


@dataclass
class GraphStats:
    nodes_by_label: dict[str, int] = field(default_factory=dict)
    edges_by_type: dict[str, int] = field(default_factory=dict)

    @property
    def total_nodes(self) -> int:
        return sum(self.nodes_by_label.values())

    @property
    def total_edges(self) -> int:
        return sum(self.edges_by_type.values())


@dataclass
class AuditReport:
    orphan_nodes: list[tuple[str, str]] = field(default_factory=list)
    events_without_provenance: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.orphan_nodes and not self.events_without_provenance


class GraphStore(ABC):
    """Common graph-store interface (section 9)."""

    @abstractmethod
    def apply_constraints(self) -> None:
        """Ensure uniqueness constraints exist before any upsert."""

    @abstractmethod
    def upsert(self, ops: GraphOps) -> None:
        """Idempotently merge nodes and relationships."""

    @abstractmethod
    def stats(self) -> GraphStats:
        """Return current node/edge counts."""


class InMemoryGraphStore(GraphStore):
    def __init__(self) -> None:
        # (label, key) -> merged props dict
        self._nodes: dict[tuple[str, str], dict[str, str]] = {}
        self._edges: set[tuple[str, str, str, str, str]] = set()

    def apply_constraints(self) -> None:
        # Keys enforce uniqueness structurally; nothing to create in memory.
        return None

    def _merge_node(self, n: Node) -> None:
        key = (n.label, n.key)
        props = self._nodes.setdefault(key, {})
        props.update(dict(n.props))

    def upsert(self, ops: GraphOps) -> None:
        for n in ops.nodes:
            self._merge_node(n)
        for edge in ops.edges:
            self._edges.add(edge)

    def stats(self) -> GraphStats:
        nodes_by_label: dict[str, int] = {}
        for label, _key in self._nodes:
            nodes_by_label[label] = nodes_by_label.get(label, 0) + 1
        edges_by_type: dict[str, int] = {}
        for _fl, _fk, rel, _tl, _tk in self._edges:
            edges_by_type[rel] = edges_by_type.get(rel, 0) + 1
        return GraphStats(nodes_by_label=nodes_by_label, edges_by_type=edges_by_type)

    def audit(self) -> AuditReport:
        connected: set[tuple[str, str]] = set()
        events_with_report: set[str] = set()
        for fl, fk, rel, tl, tk in self._edges:
            connected.add((fl, fk))
            connected.add((tl, tk))
            if rel == "REPORTS" and tl == "Event":
                events_with_report.add(tk)

        orphans = [(lbl, key) for (lbl, key) in self._nodes if (lbl, key) not in connected]
        no_prov = [
            key for (lbl, key) in self._nodes if lbl == "Event" and key not in events_with_report
        ]
        return AuditReport(orphan_nodes=orphans, events_without_provenance=no_prov)

    # Convenience accessors for tests / feature queries (Phase 05 will extend these).
    def zones_affected_by_events(self) -> dict[str, set[str]]:
        """zone_id -> set of event_ids affecting it (feeds numeric features)."""
        out: dict[str, set[str]] = {}
        for fl, fk, rel, tl, tk in self._edges:
            if rel == "AFFECTS" and fl == "Event" and tl == "H3Zone":
                out.setdefault(tk, set()).add(fk)
        return out
