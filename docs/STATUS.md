# Project Status

_Last updated: 2026-07-15_

## Current status — V2 usability update (UI, search, operator analytics)

A backward-compatible, usability-focused increment on top of V1. Scope: a redesigned rider home in
the style of consumer bike-share apps, station **search**, and a stronger **operator statistics /
analytics** screen. No forecasting/pricing/experiment claims change — everything stays offline and
honestly labelled as the `demo-heuristic-v1` demo heuristic (not a measured Phase 06 model).

- **Rider home redesign** (`apps/web/app/page.tsx`) — prominent search bar, availability summary +
  filter chips (전체 / 빌리기 좋아요 / 곧 부족), a clean station list, and a tap-to-open station
  detail sheet with the event-aware demand shift and a "why busy" trace link.
- **Station search** — new offline endpoint `GET /v2/rider/stations/search` (Korean / English /
  alias / typo-tolerant substring match over `data/fixtures/station_gazetteer.json`), which
  hydrates each hit with as-of live inventory from the operational fixture (never inferred from the
  query text). Empty query returns all stations ranked by availability.
- **Operator statistics** — new endpoint `GET /v2/operator/statistics` (real aggregations: system
  utilization, availability distribution, shortage load, event mix by type/effect, demand-delta
  spread, per-zone breakdown) rendered on a new `/statistics` screen with a stacked availability
  bar, event-type / top-surge bar lists, and a per-zone table. All values reconcile with the v1
  endpoints and respect the as-of leakage boundary.
- **Event-window timeline** — new endpoint `GET /v2/operator/timeline` recomputes the as-of
  aggregates (shortage, Δ, event count) at each hour across the replay window (12:00→18:00) with
  event-onset markers, rendered as two inline-SVG area+line charts on `/statistics`. Shows the
  leakage boundary visually (flat until onset) and `event_count` is monotonic non-decreasing.
- **Optimal extra-bike allocation** — new endpoint `POST /v2/operator/rebalancing/allocate` and
  `optimization/classical/allocation.py`: the operator inputs **M** extra bikes and the allocator
  distributes them to maximise benefit under the asymmetric objective (shortage 3 : overflow 1),
  respecting dock capacity and `Σ added ≤ M`. Objective is separable/convex so greedy is globally
  optimal (validated against brute-force enumeration). Surplus bikes with no beneficial placement
  are honestly held back, not force-placed. Rendered as a "추가 자전거 최적 분배" planner on
  `/rebalancing` with an M input.
- New code: `services/api/v2.py`, `data/fixtures/station_gazetteer.json`,
  `apps/web/app/statistics/page.tsx`; endpoints wired in `services/api/app.py`; typed client in
  `apps/web/lib/api.ts`.
- Tests: **18 new** integration tests in `tests/integration/test_api_v2.py` + **7** unit tests in
  `tests/unit/test_allocation.py` (search matching, live hydration, as-of boundary, statistics
  consistency, timeline onset/monotonicity, allocation optimality vs. brute force, honest hold-back)
  — all pass. Full non-torch suite: **204 passed, 1 skipped**; web `tsc` clean, `next build` green
  (12 routes), ruff + mypy clean on the new modules. The 9 `torch`-dependent recsys/model tests
  can't run here (the PyTorch wheel index is blocked by the container proxy) — they are unrelated
  to this change.
- **Rider / operator experience split** — a top-level role switch (🚲 라이더 / 🛠 운영자, persisted).
  Rider mode is a clean consumer view (operator tools hidden, read-only replay clock); operator mode
  shows the full tool tab bar + replay control. Deep-links to operator routes auto-select operator
  mode. Plus a **Noto Sans KR** gothic font (self-hosted via `next/font`) for Korean readability.
- **Rider map view** — a ☰ 목록 / 🗺 지도 toggle on the rider home; the map is a self-contained SVG
  that projects stations by real lat/lng (offline, no tile provider / API key), colours markers by
  availability with 🔥 surge rings, and opens the station detail sheet on click.
- **Rider copilot** — a no-LLM natural-language ask on the rider home (`POST /v2/rider/ask`).
  A deterministic parser (`services/api/rider_copilot.py`) classifies a Korean/English query into an
  allowlisted intent and answers **only from live tool results** (numbers copied verbatim, nothing
  fabricated); unsupported queries return a clarification, not a made-up answer.
- **Dynamic fare simulator** (V2-05) — a bounded scarcity surcharge (1.00/1.10/1.25/1.50) +
  balancing credit, as a **SIMULATED SHADOW** quote (never applied to a rider). Pure kernel
  (`ml/pricing/dynamic.py`) with guardrails enforced in-kernel: safety/emergency event → base,
  stale data → base, hard 1.50 cap, `base + surcharge == final` (auditable), and **no rider
  identity / reduced-fare / protected attribute** ever used. Operator `/pricing` screen with what-if
  scenario toggles. `POST /v2/pricing/quote`.
- **Ops copilot** (V2-07) — an operator NL assistant (`POST /v2/operator/ask`). A deterministic
  parser maps a query to an allowlisted intent and answers **only from the dashboard artifacts**
  (`operator_statistics` / `pricing_quotes`) — no arbitrary SQL, no fabricated numbers; facts are
  asserted to match the statistics endpoint. Answers can return a **deep-link** to the matching
  screen. Rendered as a card on `/statistics`.
- See `docs/V2_UX_UPDATE.md` for the full spec and reproduction steps.

---

## Previous status — V1 complete (with honest data blocks)

**v0 (Phases 00–09) complete**, and **V1 (V1-00 … V1-09) implemented** on top as backward-compatible
increments. See `docs/V1_EXECUTION_LOG.md` for per-phase detail and `reports/v1/V1_FINAL_AUDIT.md`
for the final audit.

- Done: V1-00 contracts · V1-01 news backfill (+ **real GDELT** opt-in) · V1-02 incremental features
  (== full rebuild) · V1-03 model registry (measured B0-B4) · V1-04 event-lift gate · V1-05
  live-shadow (pending labels) · V1-06 anomaly detection · V1-07A–D recommendation + pricing
  (measured retriever / simulated policy) · V1-08 clustered-switchback experiments (simulated) ·
  V1-09 UI (8 screens) + offline golden-path E2E + audit + packaging. Plus a **FAISS news vector
  store** (accumulating news, semantic search, same-event clustering).
- Honest blocks: **event lift** = `insufficient_event_overlap` (claim disabled); **real-news
  coverage** = `BLOCKED_DATA` until a real backfill passes the gate; **recommendation / pricing /
  experiments** = `simulated`; **live-shadow** predictions = `pending`.
- Tests: **199 passed, 1 skipped** (`make test`); web `tsc` clean; ruff clean; offline E2E green.
- Commands verified: see the `make` targets below (each runs a real, tested workflow).

---

## v0 milestone detail (Phases 00–09)

**Phase 08 — Rebalancing & Quantum Research Mode: complete.** (Phases 00–07 also complete.)

### Phase 08 — Rebalancing & Quantum Research Mode (complete)

Implemented `optimization/classical/` and `optimization/quantum/` (§14) plus the API/UI wiring:

- **Classical** (`problem.py`, `objective.py`, `feasibility.py`, `greedy.py`, `enumeration.py`,
  `milp.py`, `config/rebalancing.py`) — asymmetric operational objective (shortage > overflow,
  3:1) over post-plan inventory; explicit feasibility checks (outflow ≤ bikes, final ≤ capacity,
  non-negative integer moves, vehicle-capacity limit) that report infeasibility in plain text;
  greedy baseline (always feasible), exact **MILP** via `scipy.optimize.milp`, and an enumeration
  oracle. Verified: **MILP cost == enumeration cost** (optimal) and ≤ greedy; binding vehicle
  capacity respected.
- **Quantum Research Mode** (`qubo.py`, `qaoa.py`) — small instance → QUBO with a documented
  bounded-binary variable mapping and a quadratic imbalance surrogate energy. **QUBO brute-force
  optimum == exact enumeration optimum** (required, §14.2), encoding matches the surrogate for
  every bit vector, and on a crafted instance the QUBO plan coincides with the MILP plan. QAOA is
  optional (lazy `qiskit`); qiskit is absent here, so its test skips with a documented reason.
  Research only; simulator ≠ hardware; no advantage claim.
- **API/UI** — `POST /v1/rebalancing/solve` now returns a typed, feasibility-checked plan
  (`services/api/rebalancing.py`, `schemas.py`, `app.py`); the 501 is gone. Targets are raised in
  event-exposed zones by the `demo-heuristic-v1` forecast delta as-of the cutoff (labelled demo
  heuristic, not the measured model). `apps/web/app/rebalancing/page.tsx` renders the plan.
  `make rebalance-demo` runs the whole thing offline.

### Phase 07 — FastAPI & Next.js UI (complete)

- **API** (`services/api/`) — offline FastAPI replay service: `/v1/health`, `/v1/replay/state`,
  `/v1/replay/set-cutoff`, `/v1/events`, `/v1/forecasts`, `/v1/zones/{id}/explanation`,
  `/v1/scenarios`, `/v1/rebalancing/solve`. Every response carries mode/cutoff and model/feature
  versions; explanations are evidence-backed; the demo forecaster is the labelled
  `demo-heuristic-v1` (Historical Replay), kept distinct from the measured Phase 06 model.
- **UI** (`apps/web/`) — Next.js App Router, TS strict: Control Tower, Why Changed, Scenario Lab,
  Rebalancing Planner. Consumes the API; Historical Replay vs Live visually distinct.

### Phase 06 — Forecasting, Tuning & Evaluation (complete)

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

Run on this machine (Python 3.12.10 local; also verified on Python 3.11.15 + Node 22 in the
web/CI sandbox), `.venv`:

- `ruff check .` — passed
- `ruff format --check .` — passed (95 files)
- `mypy .` — passed (no issues, 95 source files)
- `pytest` — **114 passed, 1 skipped** (the skip is the optional QAOA test; qiskit absent).
- `make rebalance-demo` (`python -m optimization.demo`) — offline; at cutoff 15:30 greedy and
  MILP both move 8 bikes (cost 42.0 → 17.70, shortage 8 → 0, feasible); enumeration optimum
  matches the MILP; the single-edge QUBO brute-force energy equals exact enumeration (match=True).
- `apps/web`: `npm run typecheck` and `npm run build` — passed under TS strict (Next.js 15, Node 22).
- `make evaluate` (`python -m ml.forecasting.run <June zip>`) — offline; rolling-origin over
  30,947 usable rows / 139 zones. Best by CV WAPE: **knn** (`n_neighbors=30`, `weights=distance`),
  test WAPE 0.516, MASE 0.794 (beats B0 seasonal naive WAPE 0.658 / MASE 1.013). All 6 algorithms
  beat B0; top-12 reduced model matches the full 32-feature model. The domain-customised OCS
  (shortage-weighted) reorders the board (extra_trees best, knn worst learned model). Ablation
  B1=B2=B3=B4 (event features verified zero on the June window). See `README.md` and `reports/phase06_*`.
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
- Integration: `test_collectors.py` (8), `test_graph.py` (9), `test_api.py` (10 — as-of boundary
  through HTTP, evidence-backed explanations, scenario toggle, **feasible rebalancing plan**) —
  passing.
- Rebalancing/optimization: `test_rebalancing.py` (6 — pure objective, feasibility rejection,
  greedy feasibility, MILP == enumeration and ≤ greedy, binding vehicle capacity), `test_qubo.py`
  (6 + 1 skipped — bounded encoding coverage, QUBO == surrogate energy, **QUBO == enumeration
  optimum**, QUBO == MILP plan on crafted instance, QAOA degrades without qiskit).
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
  - **OCS (domain-customised, shortage-weighted 2:1) reorders the board**: the CV-WAPE pick knn is
    the *worst* learned model on OCS (0.857) because it under-forecasts most; extra_trees is best
    on OCS (0.781). All models under-forecast (negative bias) → structural stockout risk.
  - event ablation collapses to B1: 0 graph snapshots at the last June cutoff (verified, §5.2).

## Known blockers / notes

- Local `.venv` uses Python 3.12.10 (repo pins `>=3.11`; machine lacks 3.11).
- News and GBFS are still fixtures/samples (real news feed deferred by user; GBFS live is opt-in).
- Console output is ASCII-only for Windows cp949 compatibility.
- **Event lift not demonstrable on the June window**: curated events postdate the trip data, so
  the as-of event/graph features are zero and B2–B4 = B1 (verified, not assumed). See
  `docs/KNOWN_LIMITATIONS.md`. `make evaluate` requires the real June zip in `data/raw/citibike/`
  (git-ignored, §7.1); the tiny sample fixture lacks the one-week history the forecast needs.

## Known blockers / notes (Phase 08)

- `qiskit` is not installed in this environment; the QAOA path is exercised only as its
  "unavailable" branch and its test is skipped with a documented reason (§14.2). Everything else
  in Quantum Research Mode (QUBO build + brute-force + enumeration validation) runs without it.
- The rebalancing station inventory is a curated fixture (`data/fixtures/rebalancing_demo.json`);
  targets use the labelled demo heuristic, not the measured Phase 06 model. See
  `docs/KNOWN_LIMITATIONS.md`.

## Next phase input contract

**Phase 09 — Final Audit & Portfolio Packaging** consumes the completed Phases 00–08 and:
- Syncs documentation to the implementation (`docs/PRD.md`, `ARCHITECTURE.md`, `DATA_CONTRACTS.md`,
  `GRAPH_SCHEMA.md`, `OPTIMIZATION.md`, `DEMO_SCRIPT.md`, `EVALUATION_PROTOCOL.md`,
  `KNOWN_LIMITATIONS.md`, `STATUS.md`, `README.md`).
- Runs the final honesty audit (no fabricated metrics, no causal claims from feature attribution,
  no quantum-advantage claims, fixture vs live vs measured clearly separated) with the full gate
  green, per §18 and §23.
