"""Graph upsert tests. CLAUDE.md sections 9 and 17.

Covers idempotent replay (node counts do not grow), provenance/audit (no orphans, every
event reported by an article), event->zone linkage, and parameterized Cypher builders.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.collectors import NEWS_DEMO_FIXTURE
from contracts.enums import EventType, ExtractionStatus
from contracts.event import EventExtraction, EvidenceSpan, Location
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.graph import InMemoryGraphStore, upsert_events
from pipelines.graph.cypher import (
    constraint_statements,
    merge_edge_statement,
    merge_node_statement,
)
from pipelines.graph.model import NODE_KEYS

TS = datetime(2026, 7, 12, 14, 0, tzinfo=UTC)


def _demo_graph():
    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))
    store, meta = upsert_events(events, articles, store=InMemoryGraphStore())
    return store, meta, events, articles


# --- Structure ------------------------------------------------------------


def test_upsert_builds_core_nodes_and_edges():
    store, meta, events, _ = _demo_graph()
    labels = store.stats().nodes_by_label
    assert labels["Event"] == len(events)
    for required in ("Article", "Event", "EventType", "Place", "H3Zone", "Source"):
        assert labels.get(required, 0) > 0
    edges = store.stats().edges_by_type
    for rel in ("REPORTS", "INSTANCE_OF", "OCCURS_AT", "IN_ZONE", "AFFECTS", "FROM_SOURCE"):
        assert edges.get(rel, 0) > 0


def test_event_affects_at_least_one_zone():
    store, _, _, _ = _demo_graph()
    affected = store.zones_affected_by_events()
    assert affected  # events are linked to zones -> can feed numeric features


# --- Idempotency (section 9) ----------------------------------------------


def test_replay_does_not_increase_counts():
    store, _, events, articles = _demo_graph()
    n0, e0 = store.stats().total_nodes, store.stats().total_edges
    upsert_events(events, articles, store=store)  # replay identical fixture
    upsert_events(events, articles, store=store)  # and again
    assert store.stats().total_nodes == n0
    assert store.stats().total_edges == e0


# --- Provenance / audit (section 9) ---------------------------------------


def test_audit_is_clean_for_demo_graph():
    store, _, _, _ = _demo_graph()
    report = store.audit()
    assert report.clean
    assert report.orphan_nodes == []
    assert report.events_without_provenance == []


def test_event_without_source_article_is_flagged():
    # An event referencing an article that was not supplied has no REPORTS edge.
    event = EventExtraction(
        event_id="evt_orphan",
        source_article_ids=["missing"],
        event_type=EventType.TRANSIT_DISRUPTION,
        event_title="Orphan",
        event_summary="no article provided",
        published_at=TS,
        first_seen_at=TS,
        severity=0.5,
        confidence=0.8,
        locations=[Location(name="Grove St PATH", lat=40.7196, lng=-74.0431)],
        evidence_spans=[EvidenceSpan(article_id="missing", text="x")],
        extraction_model="mock-v1",
        extraction_prompt_version="mock-v1",
        status=ExtractionStatus.ACCEPTED,
    )
    store, _ = upsert_events([event], [], store=InMemoryGraphStore())
    report = store.audit()
    assert "evt_orphan" in report.events_without_provenance


def test_node_props_merge_without_duplication_on_replay():
    store, _, events, articles = _demo_graph()
    events_count = store.stats().nodes_by_label["Event"]
    upsert_events(events, articles, store=store)
    assert store.stats().nodes_by_label["Event"] == events_count


# --- Parameterized Cypher (section 9) -------------------------------------


def test_constraint_statement_per_label():
    stmts = constraint_statements()
    assert len(stmts) == len(NODE_KEYS)
    assert all("IF NOT EXISTS" in s and "IS UNIQUE" in s for s in stmts)


def test_merge_statements_are_parameterized():
    node = merge_node_statement("Event")
    assert "$key" in node and "$props" in node
    edge = merge_edge_statement("Article", "REPORTS", "Event")
    assert "$from_key" in edge and "$to_key" in edge
    # No value interpolation of user data into the statement text.
    assert "evt_" not in node


def test_merge_rejects_unknown_label_or_rel():
    with pytest.raises(ValueError):
        merge_node_statement("Bogus")
    with pytest.raises(ValueError):
        merge_edge_statement("Article", "BOGUS_REL", "Event")
