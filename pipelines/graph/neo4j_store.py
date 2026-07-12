"""Neo4j graph store. CLAUDE.md sections 9, 3, 16.

Optional backend: the ``neo4j`` driver is imported lazily so Demo Mode and tests never
require it. Writes are parameterized, idempotent MERGE statements run inside a transaction.
Uniqueness constraints are created before any upsert. Not exercised in unit tests (no live
DB); the in-memory store validates the shared upsert semantics.
"""

from __future__ import annotations

from typing import Any

from .cypher import constraint_statements, merge_edge_statement, merge_node_statement
from .model import GraphOps
from .store import GraphStats, GraphStore


class Neo4jGraphStore(GraphStore):
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
        try:
            from neo4j import GraphDatabase  # lazy: optional dependency
        except ImportError as exc:  # pragma: no cover - exercised only with the extra installed
            raise RuntimeError(
                "Neo4jGraphStore requires the 'neo4j' driver: pip install -e '.[graph]'"
            ) from exc
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def close(self) -> None:  # pragma: no cover - needs a live driver
        self._driver.close()

    def apply_constraints(self) -> None:  # pragma: no cover - needs a live driver
        with self._driver.session(database=self._database) as session:
            for stmt in constraint_statements():
                session.run(stmt)

    def upsert(self, ops: GraphOps) -> None:  # pragma: no cover - needs a live driver
        with self._driver.session(database=self._database) as session:
            session.execute_write(self._write, ops)

    @staticmethod
    def _write(tx: Any, ops: GraphOps) -> None:  # pragma: no cover - needs a live driver
        for node in ops.nodes:
            tx.run(
                merge_node_statement(node.label),
                key=node.key,
                props=dict(node.props),
            )
        for from_label, from_key, rel, to_label, to_key in ops.edges:
            tx.run(
                merge_edge_statement(from_label, rel, to_label),
                from_key=from_key,
                to_key=to_key,
            )

    def stats(self) -> GraphStats:  # pragma: no cover - needs a live driver
        nodes_by_label: dict[str, int] = {}
        edges_by_type: dict[str, int] = {}
        with self._driver.session(database=self._database) as session:
            for rec in session.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c"):
                nodes_by_label[rec["label"]] = rec["c"]
            for rec in session.run("MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS c"):
                edges_by_type[rec["rel"]] = rec["c"]
        return GraphStats(nodes_by_label=nodes_by_label, edges_by_type=edges_by_type)
