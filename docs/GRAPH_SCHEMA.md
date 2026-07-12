# Event Graph Schema (as built)

The event graph (CLAUDE.md §9) exists to turn extracted events into **numeric, as-of graph
features** (§10) — it is never used as decoration. It is backend-neutral: an offline in-memory
store (default, used by Demo Mode and tests) and an optional Neo4j backend share one
`GraphStore` interface (`pipelines/graph/`). Cypher is parameterized and idempotent; upserts
MERGE on key, so replaying the same fixture does not inflate logical node counts (proven by an
integration test).

## Nodes

| Label | Key | Notes |
|---|---|---|
| `Article` | `article_id` | source document + `raw_payload_path` provenance |
| `Event` | `event_id` | extracted event (type, effect, severity, confidence, evidence) |
| `EventType` | `event_type` | controlled ontology (§6.3) |
| `Place` | canonical name | from the place gazetteer (`config/places.py`), carries lat/lng |
| `H3Zone` | `zone_id` | H3 res-9 cell; the forecasting grain |
| `Source` | `source` | publisher of an article |
| `Station` | `station_id` | reserved for GBFS linkage (`H3Zone -[:CONTAINS]-> Station`) |

## Relationships

```
(Article)-[:REPORTS]->(Event)
(Event)-[:OCCURS_AT]->(Place)
(Place)-[:IN_ZONE]->(H3Zone)
(H3Zone)-[:CONTAINS]->(Station)
(Event)-[:AFFECTS]->(H3Zone)
(Event)-[:INSTANCE_OF]->(EventType)
(Article)-[:FROM_SOURCE]->(Source)
(Event)-[:SAME_EVENT_AS]->(Event)
```

The load-bearing path is `Article → Event → Place → H3Zone`, which materialises
`Event -[:AFFECTS]-> H3Zone` and lets a numeric feature be traced back to its source events. An
event with no path to a zone contributes nothing (and is surfaced as such in the Why-Changed
trace).

## Constraints & idempotency

- One uniqueness constraint per label (`... IF NOT EXISTS`), defined before any upsert.
- Node upserts MERGE on the key; relationship upserts MERGE on endpoints — both idempotent.
- Labels and relationship types come from a fixed allowlist; **no value interpolation** in Cypher.
- Audit flags orphan nodes and events lacking provenance (both zero on the demo graph); orphans or
  broken provenance are audit failures (§9).

## From graph to features (§10)

`pipelines/features/graph_features.py` reads the events available as-of a `forecast_cutoff`
(`available_at ≤ cutoff`, §5.2) and emits a per-zone `FeatureSnapshot`. Feature families:
`event_count_{6,24}h_by_type`, `source_weighted_severity`, `unique_source_count`,
`duplicate_article_ratio`, `confidence_mean/max`, `distance_decayed_impact`,
`time_to/since_event_start`, `event_remaining_duration`, `neighbor_zone_impact`,
`capacity_shock_exposure`, `transit_disruption_exposure`. Domain parameters (half-life, radius,
decay scale, hops, source weights, confidence floor, feature version) live in
`config/graph_features.py`, so a parameter change produces a reproducible feature change.

## Demo instance

Two curated events on 2026-07-12 link to three H3 zones (Hoboken Terminal, City Hall, Newport):
`make graph-upsert-demo` → 2 events, 15 nodes / 17 edges, idempotent replay, clean audit;
`make graph-features-demo` shows the as-of boundary (0 snapshots at 13:59 → 2 zones at 14:30 →
3 zones at 15:30 as the venue event becomes available and the transit event decays).
