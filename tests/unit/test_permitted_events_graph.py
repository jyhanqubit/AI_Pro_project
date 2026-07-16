"""NYC permitted-events -> graph adapter. CLAUDE.md §9.

Pins the mapping contract: borough-centroid grounding, ontology mapping, recurring-permit dedup
(one Event per permit id across many date rows), grounded evidence, and idempotent upsert into the
in-memory graph store.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from contracts.enums import EventType, ExtractionStatus
from pipelines.graph import build_graph_store, upsert_events
from pipelines.graph.permitted_events import load_permitted_as_events


def _write(path: Path, records: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _rec(**kw) -> dict:
    base = {
        "event_id": "100",
        "event_name": "Times Square Farmers Market",
        "start_date_time": "2026-06-01T09:00:00.000",
        "end_date_time": "2026-06-01T17:00:00.000",
        "event_type": "Farmers Market",
        "event_borough": "Manhattan",
        "event_location": "BROADWAY between W 42 ST and W 43 ST",
        "street_closure_type": "",
    }
    base.update(kw)
    return base


def test_maps_borough_ontology_and_grounds_evidence(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl.gz"
    _write(p, [_rec(event_type="Parade", event_name="Pride Parade")])
    events, articles = load_permitted_as_events(p)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type is EventType.PUBLIC_GATHERING  # Parade -> PUBLIC_GATHERING
    assert ev.status is ExtractionStatus.ACCEPTED
    assert ev.locations[0].lat == 40.776 and ev.locations[0].lng == -73.971  # Manhattan centroid
    # Evidence is grounded in the synthetic record text (the event name).
    assert ev.evidence_spans[0].text == "Pride Parade"
    assert articles[ev.source_article_ids[0]].source == "NYC Open Data - Permitted Events"


def test_recurring_permit_collapses_to_one_event(tmp_path: Path) -> None:
    # Same permit id across three date rows -> a single Event (recurring market).
    p = tmp_path / "ev.jsonl.gz"
    _write(
        p,
        [
            _rec(event_id="777", start_date_time="2026-06-06T09:00:00.000"),
            _rec(event_id="777", start_date_time="2026-06-13T09:00:00.000"),
            _rec(event_id="777", start_date_time="2026-06-20T09:00:00.000"),
        ],
    )
    events, _ = load_permitted_as_events(p)
    assert len(events) == 1


def test_closure_sets_capacity_decrease_and_limit_counts_distinct(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl.gz"
    _write(
        p,
        [
            _rec(event_id="1", street_closure_type="Full Street Closure"),
            _rec(event_id="2", event_borough="Brooklyn"),
            _rec(event_id="3", event_borough="Queens"),
        ],
    )
    events, _ = load_permitted_as_events(p, limit=2)  # limit = distinct permits
    assert len(events) == 2
    assert events[0].capacity_effect.value == "decrease"  # closure removes capacity


def test_unmappable_borough_is_skipped(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl.gz"
    _write(p, [_rec(event_borough="Nowhere"), _rec(event_id="2", event_borough="Bronx")])
    events, _ = load_permitted_as_events(p)
    assert len(events) == 1
    assert events[0].locations[0].name.endswith("(Bronx)")


def test_upsert_is_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "ev.jsonl.gz"
    _write(p, [_rec(event_id="1"), _rec(event_id="2", event_borough="Brooklyn")])
    events, articles = load_permitted_as_events(p)
    store = build_graph_store("memory")
    upsert_events(events, list(articles.values()), store=store)
    before = store.stats().total_nodes
    upsert_events(events, list(articles.values()), store=store)  # replay
    assert store.stats().total_nodes == before  # logical counts unchanged (§9)
    assert store.audit().clean
