# Project Status

_Last updated: 2026-07-13_

## Current completed phase

**Phase 06 — Forecasting, Tuning & Evaluation: complete.** (Phases 00–05 also complete.)

Implemented `ml/forecasting/` (§11): a seasonal-naive baseline, a six-algorithm model zoo,
rolling-origin temporal CV, GridSearch tuning, permutation-importance feature selection, the
B0–B4 ablation, and the §11.4 metrics — run on the real June-2026 data.

- **No leakage in evaluation** (`splits.py`) — the latest 72h are an untouched out-of-sample
  test; GridSearch cross-validates on the earlier span with 3 expanding-window folds; imputation
  and scaling are fit per fold. Random K-fold is never used (§11.3).
- **Model zoo + GridSearch** (`models.py`, `config/forecasting.py`) — ridge, knn, random_forest,
  extra_trees, gradient_boosting, hist_gradient_boosting, each with a tuned grid; seed 42.
- **Metrics** (`metrics.py`) — WAPE (defined zero-denominator), MAE, MASE (explicit seasonal
  scale), event-window WAPE, peak-direction accuracy, forecast-delta stability.
- **Feature selection** (`feature_selection.py`) — permutation importance on the test holdout;
  the top-12 reduced model matches the full 32-feature model.
- **Honest event ablation** — the runner verifies (not assumes) that as-of event/graph features
  are zero on the June window (curated events postdate the data, §5.2), so B2–B4 reproduce B1.
  Reported plainly (§11.4, §22); interpretation and figures in `README.md` / `docs/`.

### Phase 05 — As-of Graph Feature Builder (complete)

Implemented `pipelines/features/graph_features.py` + `kernels.py` (§10, §5.2):

- **Pure kernels** (`kernels.py`) — `haversine_km`, `exp_distance_decay`, `half_life_weight`;
  side-effect free and unit-tested (§10 "mathematical kernel as pure functions").
- **Builder** (`build_graph_features`) — for a `forecast_cutoff`, emits per-zone
  `FeatureSnapshot`s using ONLY events with `available_at <= cutoff` (§5.2). Produces the §10
  feature set: `event_count_{6,24}h_by_type`, `source_weighted_severity`, `unique_source_count`,
  `duplicate_article_ratio`, `confidence_mean/max`, `distance_decayed_impact`,
  `time_to/since_event_start`, `event_remaining_duration`, `neighbor_zone_impact`,
  `capacity_shock_exposure`, `transit_disruption_exposure`. Preserves `source_event_ids`.
- **Config-reproducible** (`config/graph_features.py`, `GraphFeatureConfig`) — half-life,
  radius, decay scale, hops, source weights, confidence floor, feature version. Same events +
  same cutoff + same config → identical output.

### Phase 04 — Neo4j Graph Upsert (complete)

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
- `ruff format --check .` — passed (76 files)
- `mypy .` — passed (no issues, 76 source files)
- `pytest` — **90 passed**
- `make evaluate` (`python -m ml.forecasting.run <June zip>`) — offline; rolling-origin over
  30,947 usable rows / 139 zones. Best by CV WAPE: **knn** (`n_neighbors=30`, `weights=distance`),
  test WAPE 0.516, MASE 0.794 (beats B0 seasonal naive WAPE 0.658 / MASE 1.013). All 6 algorithms
  beat B0; top-12 reduced model matches the full 32-feature model. Ablation B1=B2=B3=B4 (event
  features verified zero on the June window). See `README.md` and `reports/phase06_*`.
- `make graph-upsert-demo` — offline; 2 events → 15 nodes / 17 edges; idempotent replay; audit
  clean; events link to 3 H3 zones.
- `make graph-features-demo` — offline; shows the as-of boundary: cutoff 13:59 → 0 snapshots
  (transit event not yet available); 14:30 → 2 zones (transit_disruption_exposure ≈ 0.63);
  15:30 → 3 zones as the concert becomes available and the transit event decays.
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
  `test_demand_features.py` (12), `test_calendar.py` (5), `test_event_extraction.py` (9),
  `test_graph_features.py` (10, incl. the **14:01→14:00 leakage regression**) — passing.
- Integration: `test_collectors.py` (8), `test_graph.py` (9) — passing (idempotent replay,
  provenance audit, event→zone linkage, parameterized Cypher).
- Forecasting: `test_forecasting.py` (10) — WAPE/MASE zero-denominator behaviour, seasonal-naive
  fallback, and the rolling-origin guarantee that every training fold precedes its validation
  window (no temporal leakage, §11.3).
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
- **Forecasting (Phase 06)** on the same data (rolling-origin, seed 42; `make evaluate`):
  - dev 26,918 / out-of-sample test 4,029 rows (last 72h), 3 expanding CV folds, 32 B1 features.
  - leaderboard (test WAPE): extra_trees 0.492, gradient_boosting 0.497, hist_gb 0.497,
    random_forest 0.505, knn 0.516, ridge 0.527; B0 seasonal naive 0.658. CV-selected model: knn.
  - top features by permutation importance: `dep_lag_1`, `dep_lag_168`, `arr_lag_1`, `dep_lag_24`,
    `cal_hour_cos`, `cal_is_evening_rush` — short-term persistence + weekly seasonality + rush timing.
  - event ablation collapses to B1: 0 graph snapshots at the last June cutoff (verified, §5.2).

## Known blockers / notes

- Local `.venv` uses Python 3.12.10 (repo pins `>=3.11`; machine lacks 3.11).
- News and GBFS are still fixtures/samples (real news feed deferred by user; GBFS live is opt-in).
- Console output is ASCII-only for Windows cp949 compatibility.
- **Event lift not demonstrable on the June window**: curated events postdate the trip data, so
  the as-of event/graph features are zero and B2–B4 = B1 (verified, not assumed). See
  `docs/KNOWN_LIMITATIONS.md`. `make evaluate` requires the real June zip in `data/raw/citibike/`
  (git-ignored, §7.1); the tiny sample fixture lacks the one-week history the forecast needs.

## Next phase input contract

**Phase 07 — FastAPI & Next.js UI** consumes:
- The forecasting outputs (`ml/forecasting/run.py` → `reports/phase06_results.json`) and the
  as-of event graph / feature snapshots, surfaced through the §12 API endpoints
  (`/v1/forecasts`, `/v1/zones/{id}/explanation`, `/v1/replay/*`, `/v1/scenarios`).
- Drives the §13 operator UI (Control Tower → Why Changed → Scenario Lab → Rebalancing) from
  fixtures, with Historical Replay and Live visually distinct. Evidence-free explanations are
  forbidden; the golden-path demo must run entirely offline.
