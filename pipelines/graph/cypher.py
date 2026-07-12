"""Parameterized Cypher builders. CLAUDE.md sections 9 and 16.

Pure string builders so the statements are unit-testable without a database. Only
parameterized Cypher is produced (no string-interpolated values), and all writes are
idempotent MERGE. Labels/relationship types come from a fixed allowlist, never user input.
"""

from __future__ import annotations

from .model import NODE_KEYS, REL_TYPES


def constraint_statements() -> list[str]:
    """One uniqueness constraint per node label, created only if absent."""
    stmts = []
    for label, key in NODE_KEYS.items():
        stmts.append(
            f"CREATE CONSTRAINT {label.lower()}_{key}_unique IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
        )
    return stmts


def merge_node_statement(label: str) -> str:
    """MERGE a node on its key and set the remaining properties from $props."""
    if label not in NODE_KEYS:
        raise ValueError(f"unknown node label: {label!r}")
    key = NODE_KEYS[label]
    return f"MERGE (n:{label} {{{key}: $key}}) SET n += $props"


def merge_edge_statement(from_label: str, rel: str, to_label: str) -> str:
    """MERGE a relationship between two nodes matched on their keys."""
    if from_label not in NODE_KEYS or to_label not in NODE_KEYS:
        raise ValueError("unknown node label in edge")
    if rel not in REL_TYPES:
        raise ValueError(f"unknown relationship type: {rel!r}")
    fk, tk = NODE_KEYS[from_label], NODE_KEYS[to_label]
    return (
        f"MATCH (a:{from_label} {{{fk}: $from_key}}) "
        f"MATCH (b:{to_label} {{{tk}: $to_key}}) "
        f"MERGE (a)-[:{rel}]->(b)"
    )
