# Project Status

_Last updated: 2026-07-12_

## Current completed phase

**Phase 04 — Neo4j Graph Upsert: complete.** (Phases 00–03 also complete.)

Implemented `pipelines/graph/` — a backend-neutral event graph (§9):

- **Model** (`model.py`) — `build_graph_ops` turns events + their source articles into the §9
  node/relationship set: Article, Event, EventType, Place, H3Zone, Source (Station reserved),
  wiring `Event -[:AFFECTS]-> H3Zone` via `Event -> Place -> H3Zone` so the graph feeds numeric
  features (a graph that couldn't is forbidden decoration, §9). A small place gazetteer
  (`config/places.py`) lets the mock extractor attach grounded locations to events.
- **Stores** (`store.py`, `neo4j_store.py`) — a `GraphStore` interface with an **offline
  in-memory** backend (idempotent MERGE semantics; Demo/tests need no DB) and an optional
  **Neo4j** backend using parameterized, idempotent Cypher (lazy driver import, `.[graph]` extra).
- **Cypher** (`cypher.py`) — pure, unit-tested builders: one uniqueness constraint per label
  (`IF NOT EXISTS`), MERGE-on-key node upserts, MERGE relationship upserts. Labels/rel-types
  come from a fixed allowlist; no value interpolation.
- **Audit** — flags orphan nodes and events lacking provenance (both zero on the demo graph).

### Phase 03 — LLM Event Extraction (complete)

Implemented `pipelines/events/` with a provider interface and a deterministic mock (§8):

- **Provider** (`provider.py`) — `LlmProvider` ABC + `MockLlmProvider`: keyword-ontology
  extractor, no network/key. Same fixture + prompt version → identical output; stable event ids.
  Evidence spans are exact substrings of the article (grounded); per-type demand/capacity effect
  is directional only (e.g. transit disruption → bike demand *increase*), severity is a bounded prior.
- **Extractor** (`extractor.py`) — validates candidates with Pydantic under **bounded retries**,
  verifies evidence grounding, sets accept/quarantine/reject from a configurable confidence
  threshold, and **deduplicates** near-identical events (token-Jaccard, merging provenance).
  Rejected/quarantined events are kept (auditable); the final validation error is recorded on failure.
- Config (`config/events.py`): keyword ontology, effect priors, thresholds, dedup — all tunable.

### Phase 02 — Demand Aggregation & Feature Store (complete)

Implemented the demand feature pipeline in `pipelines/features/`:

- **Temporal kernels** (`temporal.py`) — pure functions localizing naive wall-clock times to
  `America/New_York` with **explicit DST handling**: spring-forward (nonexistent) times are
  shifted across the gap, fall-back (ambiguous) times resolve to the earlier occurrence — never
  silently dropped (§5.3). Plus local-hour flooring and a gap-free hourly index that yields the
  correct 23/25-hour DST days. The Citi Bike collector now uses this localization too.
- **Zone assignment** (`zones.py`) — H3 res-9 cell per coordinate (§4), thin wrapper over `h3`.
- **Aggregation** (`aggregate.py`) — trips → `DemandCell` at the primary grain (H3 zone × local
  hour): departures at start, arrivals at end, `net_flow = arrivals - departures`. New contract
  `DemandCell` (§4, §6).
- **Leakage-safe features** (`lags.py`) — per-zone dense hourly reindex (missing hours = 0),
  lag features (1h/24h/168h) and shifted rolling means (3h/24h). Every feature at hour t uses
  strictly hours < t; the current target never enters its own feature; no wrap across zones (§5.4).
- **Calendar features** (`calendar.py`) — completes ablation B1's "calendar" layer (§11.2):
  hour-of-day, day-of-week, weekend, morning/evening rush, US federal holiday, and cyclical
  (sin/cos) encodings for hour and weekday. These describe the target hour and are leakage-free.
  Total feature width is now 25 (15 lag/rolling + 10 calendar) plus 3 labels.

## Commands verified

Run on this machine (Python 3.12.10, `.venv`):

- `ruff check .` — passed
- `ruff format --check .` — passed (60 files)
- `mypy .` — passed (no issues, 60 source files)
- `pytest` — **70 passed**
- `make graph-upsert-demo` — offline; 2 events → 15 nodes / 17 edges; replay leaves counts
  unchanged (idempotent); audit clean (0 orphans, 0 events without provenance); events link to
  3 H3 zones (Hoboken Terminal + City Hall for the transit disruption, Newport for the concert).
- EDA on the real June-2026 data (`docs/EDA.md`, `docs/STATISTICAL_TESTS.md`): derived 7
  leakage-safe features (surge momentum, zone expanding mean, same-day net-flow pressure, and
  two member-share composition lags); feature width now **32**.
- Statistical verification (scipy): weekday vs weekend is driven by **timing** (evening rush
  Cohen's d = 2.20) and **rider composition** (member share d = 2.72, p = 1.4e-4), not by daily
  totals (Welch p = 0.15). Day-of-week significant (Kruskal p = 0.017); rideable_type not
  significant for rush (chi-square p = 0.50) → deliberately not added as a feature.
- Visual EDA report published as an Artifact (offline, self-contained; charts + tests).
- `make collect-demo` — runs fully offline (see prior phase output).
- `make build-features` (`python -m pipelines.features.demo`) — offline on the sample fixture:
  trips=4, demand_cells=7, feature_rows=7, zones=4.
- `make extract-events-demo` (`python -m pipelines.events.demo`) — offline; from 3 fixture
  articles: 2 accepted events (TRANSIT_DISRUPTION → demand increase; LARGE_VENUE_EVENT), 0
  errors, evidence grounded; the neutral article yields no event.

## Tests passing / failing

- Unit: `test_contracts.py` (19), `test_settings.py` (3), `test_temporal.py` (6),
  `test_demand_features.py` (12), `test_calendar.py` (5), `test_event_extraction.py` (9) — passing.
- Integration: `test_collectors.py` (8), `test_graph.py` (9) — passing (idempotent replay,
  provenance audit, event→zone linkage, parameterized Cypher).
- Temporal coverage includes **DST spring-forward and fall-back** cases (§5.3) and the
  **lag/rolling leakage** guarantees (§5.4), including "changing the current value does not
  change any past feature".

## Measured results available

- **Real-data run** on `JC-202606-citibike-tripdata.csv.zip` (June 2026, git-ignored per §7.1),
  full pipeline in ~4.7s:
  - collection: total=109,897, accepted=109,510, excluded=387 (all `missing_coordinate`, verified).
  - aggregation: **40,479 demand cells across 208 H3 zones**.
  - features: 40,479 rows; 30,947 have a 1-week (168h) lag available.
  - busiest cell: 2026-06-09 17:00 (evening rush) — departures=87, arrivals=13, net=-74.
- No forecasting models trained yet (Phase 06).

## Known blockers / notes

- Local `.venv` uses Python 3.12.10 (repo pins `>=3.11`; machine lacks 3.11).
- News and GBFS are still fixtures/samples (real news feed deferred by user; GBFS live is opt-in).
- Console output is ASCII-only for Windows cp949 compatibility.

## Next phase input contract

**Phase 05 — As-of Graph Feature Builder** consumes:
- The event graph (`store.zones_affected_by_events()` and richer queries) plus event
  timestamps, at a given `forecast_cutoff`.
- Produces the numeric `FeatureSnapshot` features in §10 (event_count_*_by_type,
  source_weighted_severity, distance_decayed_impact, time_to_event_start,
  transit_disruption_exposure, neighbor_zone_impact, …) as **pure functions**, versioned and
  reproducible, using only events with `available_at <= forecast_cutoff` (§5.2 leakage rule).
