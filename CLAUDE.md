# ShockFlow AI — Claude Code Repository Instructions

This file is the persistent operating contract for Claude Code in this repository.
Phase-specific prompts define **what to implement now**; this file defines **how the repository must be understood and changed at all times**.

---

## 1. Mission

Build **ShockFlow AI**, an event-aware urban mobility demand forecasting and fleet rebalancing decision-support system.

Canonical product flow:

```text
Citi Bike demand history
+ timestamped news / event input
+ current station inventory
→ LLM event extraction
→ Neo4j event graph
→ as-of numeric graph features
→ H3 zone-hour demand forecast
→ explanation and scenario comparison
→ feasible rebalancing plan
```

The portfolio must demonstrate a real end-to-end system, not disconnected notebooks or mocked screenshots.

The central product claim is:

> ShockFlow AI detects irregular demand shocks from timestamped events, converts them into traceable graph features, quantifies their model-attributed forecast impact, and turns the forecast into an operational action.

Do not describe model attribution as proven causality.

---

## 2. MVP Scope

The initial MVP uses only three primary data sources.

1. **Citi Bike Trip History**
   - Batch, historical demand labels.
   - Local CSV or ZIP input is sufficient.
   - Automatic remote backfill is optional, not required for Demo Mode.

2. **Demo News Fixture**
   - JSONL events replayed in publication-time order.
   - Used for deterministic Historical Replay and evaluation.

3. **Citi Bike GBFS `station_status`**
   - Current station inventory and operating state.
   - Supports fixture-based Demo Mode and optional live polling.

The following are optional extensions and must not be introduced into the critical path unless the active phase explicitly requests them:

- GDELT live news
- MTA service alerts
- weather APIs
- NYC permitted events
- Kafka
- Airflow
- cloud-managed databases
- online model retraining
- live quantum hardware

A smaller, fully reproducible vertical slice is preferred over a broad but fragile architecture.

---

## 3. Operating Modes

Every record, API response, UI view, and artifact must make its operating mode explicit.

Supported values:

```text
demo_fixture
historical_replay
live
research
```

Rules:

- **Demo Mode must work without external API keys.**
- Historical Replay is the default presentation mode.
- Live collectors are disabled by default.
- A live collector failure must never break Demo Mode.
- Research Mode is used for QUBO/QAOA experiments only.
- Research Mode outputs must never feed Demo, Historical Replay, or Live views, and simulator results must never be labeled as hardware results.
- Never display fixture data as live data.
- Never display simulator output as hardware output.

Recommended environment default:

```env
SHOCKFLOW_MODE=demo_fixture
ENABLE_GBFS_LIVE=false
ENABLE_GDELT_LIVE=false
LLM_PROVIDER=mock
```

---

## 4. Domain Invariants

These rules are non-negotiable.

1. The primary forecasting grain is **H3 zone × local hour**.
2. Primary targets are:

   ```text
   departures
   arrivals
   net_flow = arrivals - departures
   ```

3. The LLM does not directly forecast numerical demand.
4. The LLM may extract event type, location, time, severity prior, effect direction, mechanism, confidence, and evidence.
5. Every accepted event must have source provenance and non-empty evidence spans.
6. Every model feature must be reproducible as of a forecast cutoff.
7. Every graph-derived feature must be numeric, versioned, persisted, and testable.
8. Every forecast must identify model version, feature version, forecast cutoff, and horizon.
9. Rebalancing output must be checked for feasibility before presentation.
10. No fabricated metrics, API responses, model results, citations, or performance claims.
11. A lack of model improvement must be reported honestly.
12. “Model-attributed impact” is acceptable wording; “causal impact” is not unless a causal design has actually been implemented and validated.

---

## 5. Temporal Semantics and Leakage Prevention

Temporal correctness is more important than model complexity.

### 5.1 Required timestamps

Keep these fields distinct when applicable:

```text
published_at     # when information became publicly available
first_seen_at    # when this system first observed it
event_start_at   # when the real-world event starts
event_end_at     # known or expected event end
fetched_at       # when a collector fetched the payload
ingested_at      # when the system persisted the record
forecast_cutoff  # information boundary for a prediction
```

All timestamps must be timezone-aware.

### 5.2 Availability rule

For event-derived features:

```text
available_at = max(published_at, first_seen_at)
```

An event may be used only when:

```text
available_at <= forecast_cutoff
```

A past `event_start_at` does not make an event available before it was published or observed.

### 5.3 Storage and local-time aggregation

- Persist canonical timestamps in UTC.
- Preserve source timestamp text when useful for auditability.
- Convert trip timestamps to `America/New_York` before hourly demand aggregation.
- Treat DST transitions explicitly; never silently drop ambiguous or nonexistent local times.
- Unit-test spring-forward and fall-back cases.

### 5.4 Lag and rolling rules

- The current target value must never appear in its own lag or rolling feature.
- Rolling windows must be shifted before aggregation.
- Random train/test split is forbidden.
- All model variants in an ablation must use identical cutoffs and split windows.

Minimum leakage regression test:

```text
Given an article first available at 14:01,
when building features for a 14:00 cutoff,
then every feature contribution from that article must be zero or absent.
```

Never weaken or delete leakage tests to make a pipeline pass.

---

## 6. Data Contracts

Typed contracts are required at service and pipeline boundaries.

Use Pydantic models for application boundaries and explicit schemas for Parquet/CSV outputs.

### 6.1 Trip record

Canonical minimum fields:

```text
trip_id or deterministic row key
started_at
ended_at
start_station_id
end_station_id
start_lat
start_lng
end_lat
end_lng
source_file
loaded_at
```

Validate or report:

- missing coordinates
- invalid latitude/longitude
- end time before start time
- implausible duration
- duplicate rows
- source column aliases

Do not silently discard bad records. Record excluded row counts and reasons in metadata.

### 6.2 Article record

Canonical minimum fields:

```text
article_id
title
text or permitted snippet
source
published_at
first_seen_at
available_at
url_hash
mode
raw_payload_path
```

### 6.3 Event extraction

Canonical minimum fields:

```text
event_id
source_article_ids
event_type
event_title
event_summary
published_at
first_seen_at
available_at
event_start_at
event_end_at
locations[]
demand_effect
capacity_effect
severity
confidence
evidence_spans[]
extraction_model
extraction_prompt_version
status
```

Accepted event ontology:

```text
TRANSIT_DISRUPTION
WEATHER_SHOCK
LARGE_VENUE_EVENT
ROAD_CLOSURE
PUBLIC_GATHERING
SAFETY_INCIDENT
SYSTEM_ALERT
OTHER
```

Rejected or low-confidence extractions must remain auditable; do not silently erase them.

### 6.4 Feature snapshot

Canonical minimum fields:

```text
zone_id
forecast_cutoff
feature_version
source_event_ids
feature values...
created_at
```

Each snapshot must allow a reviewer to trace a numeric feature back to its source events.

### 6.5 Forecast output

Canonical minimum fields:

```text
zone_id
forecast_cutoff
forecast_horizon
model_version
feature_version
target_name
baseline_forecast
p10                  # optional; omit or null if no calibrated interval
p50                  # optional; omit or null if no calibrated interval
p90                  # optional; omit or null if no calibrated interval
event_aware_forecast
forecast_delta
mode
```

Do not invent uncertainty intervals. If the model does not produce calibrated intervals, omit them or label them as unavailable.

---

## 7. Data Collection Rules

### 7.1 Citi Bike Trip History

- MVP reads local CSV or ZIP files under `data/raw/citibike/`.
- Column aliases belong in configuration, not scattered conditionals.
- Save source filename, row count, schema hash, load timestamp, and exclusion statistics.
- Do not commit large raw trip files to Git.
- Provide a small legal sample fixture for tests.

### 7.2 Demo News Fixture

- Input format is JSONL.
- Replay strictly follows `available_at`, not event start time.
- Deduplicate on `article_id` and/or `url_hash`.
- Invalid timestamps fail with a precise message.
- The fixture must include at least one event crossing the 13:59 → 14:00 golden-path boundary.

### 7.3 GBFS Station Status

- Implement a common collector interface.
- Fixture mode is mandatory.
- Live mode is optional and disabled by default.
- Use request timeout, bounded retry, and explicit error handling.
- Persist `fetched_at`, source update time, payload hash, and raw payload path.
- Live failure returns a degraded-state warning; it must not corrupt stored state or stop Demo Mode.

### 7.4 Optional collectors

Optional collectors must be isolated behind configuration flags and provider interfaces.

They may not:

- add a mandatory API key to Demo Mode
- alter canonical data contracts without a documented migration
- bypass provenance fields
- make tests depend on the public internet

---

## 8. LLM Event Extraction Rules

The extraction layer must have a provider interface and a deterministic mock provider.

Required provider behavior:

```text
same fixture input + same prompt version → same mock output
```

Rules:

- Validate all output with Pydantic before persistence.
- Require evidence spans grounded in the input text.
- Do not infer precise demand percentages.
- `severity` is an ordinal or bounded prior, not an observed causal effect.
- Use bounded retries for malformed structured output.
- Record the final validation error when extraction fails.
- Keep prompt version and model identifier in every extraction.
- Low-confidence output is rejected or quarantined based on configuration.
- Deduplication thresholds must be configurable and tested.

Do not send secrets, personal data, or entire licensed articles to an external provider.

---

## 9. Neo4j Graph Contract

Core nodes:

```text
Article
Event
Place
H3Zone
Station
EventType
Source
```

Core relationships:

```text
(Article)-[:REPORTS]->(Event)
(Event)-[:OCCURS_AT]->(Place)
(Place)-[:IN_ZONE]->(H3Zone)
(H3Zone)-[:CONTAINS]->(Station)
(Event)-[:AFFECTS]->(H3Zone)
(Event)-[:INSTANCE_OF]->(EventType)
(Article)-[:FROM_SOURCE]->(Source)
(Event)-[:SAME_EVENT_AS]->(Event)
```

Rules:

- Define uniqueness constraints before upserts.
- Use parameterized Cypher only.
- Upserts must be idempotent.
- Preserve source identifiers and raw payload paths.
- Do not use Neo4j solely for visualization; graph output must feed numeric forecasting features.
- Integration tests must prove that replaying the same fixture does not increase logical node counts.
- Orphan nodes and broken provenance paths are audit failures.

---

## 10. Graph Feature Contract

Minimum graph features:

```text
event_count_6h_by_type
event_count_24h_by_type
source_weighted_severity
unique_source_count
duplicate_article_ratio
confidence_mean
confidence_max
distance_decayed_impact
time_to_event_start
time_since_event_start
event_remaining_duration
neighbor_zone_impact
capacity_shock_exposure
transit_disruption_exposure
```

Configurable domain parameters:

```text
event_type half-life
geographic radius
confidence threshold
maximum graph hops
source weight
deduplication threshold
distance decay function
```

Rules:

- Implement the mathematical kernel as pure functions where practical.
- Persist configuration and feature version with every snapshot.
- Preserve source event IDs.
- Deterministic input and cutoff must produce deterministic output.
- A feature change caused by a parameter change must be reproducible from configuration.

---

## 11. Forecasting and Evaluation

### 11.1 Model order

Implement in this order:

1. Seasonal Naive
2. Global tree baseline
3. Event-aware tree model
4. Optional spatial or deep model only after the ablation is valid

Do not start with a GNN or Transformer before the baseline pipeline and leakage tests pass.

### 11.2 Required ablation

```text
B0: Seasonal Naive
B1: demand history + calendar
B2: B1 + raw article counts
B3: B1 + LLM event features
B4: B3 + graph-propagated features
```

Weather is not required in the initial MVP.

### 11.3 Split strategy

Use rolling-origin or expanding-window evaluation.

Never use random K-fold for temporal forecasting.

### 11.4 Metrics

Minimum metrics:

```text
WAPE
MAE
MASE
event-window WAPE
peak direction accuracy
forecast delta stability
```

Rules:

- Define zero-denominator behavior for WAPE.
- Calculate MASE against an explicit seasonal naive scale.
- Report overall and event-window performance separately.
- Generate metrics only from executed experiments.
- Save exact split boundaries, seed, features, model parameters, and versions.
- If event-aware features do not improve performance, report the result and analyze why.

### 11.5 Tuning

Tunable layers may include:

```text
model hyperparameters
lag and rolling windows
event half-life
geographic radius
confidence threshold
dedup threshold
operational cost weights
```

Keep search spaces in configuration.

The best trial must be reproducible from a saved config. Failed trials must remain visible in logs.

---

## 12. API Contract

Expected endpoints:

```text
GET  /v1/health
GET  /v1/replay/state
POST /v1/replay/set-cutoff
GET  /v1/events
GET  /v1/forecasts
GET  /v1/zones/{zone_id}/explanation
POST /v1/scenarios
POST /v1/rebalancing/solve
```

Rules:

- Use Pydantic request and response models.
- Keep OpenAPI output consistent with implementation.
- Return mode, cutoff, model version, and feature version where relevant.
- Return structured error codes and human-readable messages.
- Never return evidence-free explanations.
- A live dependency outage should return degraded status, not a fabricated success.

---

## 13. UI/UX Contract

Primary interaction flow:

```text
Alert → Why → Simulate → Act
```

Required screens:

1. **Control Tower**
   - map or zone-risk overview
   - forecast horizon and replay time
   - event alerts
   - baseline vs event-aware forecast
   - inventory/risk state

2. **Why Changed**
   - evidence article or source alert
   - Article → Event → H3Zone → Feature trace
   - model-attributed forecast delta

3. **Scenario Lab**
   - event on/off
   - severity, duration, radius, and cost controls where supported
   - baseline and scenario comparison

4. **Rebalancing Planner**
   - origin, destination, moved quantity, distance/cost, feasibility
   - shortage and overflow reduction estimates

Rules:

- The first screen is an operator view, not a raw graph explorer.
- Historical Replay and Live Mode must be visually distinct.
- Implement loading, empty, error, and degraded states.
- Do not display placeholder KPIs as measured results.
- Do not imply causal certainty.
- The golden-path demo must run entirely from fixtures.

---

## 14. Rebalancing and Quantum Research Mode

### 14.1 Classical optimization

Implement in this order:

1. Greedy feasible baseline
2. Classical MILP or another explicit constrained solver
3. Small-instance QUBO conversion
4. Exact QUBO validation
5. Optional QAOA simulator

The operational objective may include:

```text
expected shortage cost
overflow cost
relocation distance cost
vehicle capacity penalty
constraint violation penalty
```

Required constraints:

- cannot move more units than available at origin
- cannot exceed destination capacity
- non-negative integer movement
- respect total movement or vehicle capacity limit
- report infeasibility explicitly

### 14.2 Quantum rules

- Label all QUBO/QAOA functionality as **Quantum Research Mode**.
- Do not claim quantum advantage.
- Do not call simulator results hardware results.
- Document the mapping from operational variables to QUBO variables.
- Validate the small QUBO objective against exact enumeration.
- If Qiskit is absent, skip optional tests with a documented reason.

---

## 15. Repository Structure

Use the existing structure unless a phase explicitly changes it.

```text
apps/web/
services/api/
pipelines/collectors/
pipelines/events/
pipelines/features/
ml/forecasting/
optimization/classical/
optimization/quantum/
data/fixtures/
data/raw/
data/processed/
config/
docs/
reports/
tests/unit/
tests/integration/
tests/e2e/
```

Do not move large parts of the repository without a documented architecture reason.

Generated artifacts, raw large datasets, model binaries, secrets, and local database volumes must be ignored by Git unless a small fixture is intentionally versioned.

---

## 16. Engineering Standards

### Python

- Python 3.11 or the version pinned by the repository.
- Type hints on public functions.
- Pydantic v2 for service-boundary models when available.
- `pathlib` rather than string path concatenation.
- Explicit timezones; avoid naive `datetime`.
- Deterministic random seeds.
- Small pure functions for temporal kernels and feature calculations.
- No broad `except Exception: pass`.
- Log errors with context but never log secrets.

### Frontend

- TypeScript strict mode.
- Typed API clients or generated types where practical.
- Accessible labels and keyboard-reachable controls.
- No hard-coded fake business metrics.
- Keep map/graph rendering separate from domain state logic.

### SQL/Cypher

- Parameterized statements only.
- Idempotent migrations and graph upserts.
- Explicit indexes and uniqueness constraints.
- No destructive reset in normal startup commands.

### Configuration

- Runtime settings belong in typed configuration or environment variables.
- Search spaces belong in YAML/TOML/typed config, not hidden in notebooks.
- `.env.example` documents variables without secrets.
- Demo defaults must be safe and offline-compatible.

---

## 17. Testing Standards

Required test layers:

### Unit tests

- timestamp parsing
- DST behavior
- trip normalization
- lag and rolling leakage
- event schema validation
- evidence requirement
- event deduplication
- as-of filtering
- graph feature kernels
- metric calculations
- optimizer feasibility

### Integration tests

- fixture collection to persisted record
- Neo4j constraints and idempotent upsert
- feature snapshot provenance
- API schema and repository boundary

### End-to-end test

The minimum golden path is:

```text
1. Set replay cutoff to 13:59.
2. Confirm the 14:00 event is unavailable.
3. Advance cutoff to 14:00.
4. Extract and persist the event.
5. Update the graph.
6. Rebuild the affected zone feature snapshot.
7. Recompute the event-aware forecast.
8. Return evidence and graph path through the API.
9. Display forecast delta in the UI.
10. Toggle the event off in Scenario Lab.
11. Produce a feasible rebalancing plan.
```

Tests must not rely on the public internet.

Do not delete, skip, or loosen a failing test merely to complete a phase. Fix the defect or document a genuine environment-specific skip.

---

## 18. Documentation Synchronization

When behavior or contracts change, update the relevant documents in the same change.

At minimum, inspect:

```text
docs/PRD.md
docs/ARCHITECTURE.md
docs/DATA_CONTRACTS.md
docs/GRAPH_SCHEMA.md
docs/EVALUATION_PROTOCOL.md
docs/DEMO_SCRIPT.md
docs/KNOWN_LIMITATIONS.md
docs/STATUS.md
README.md
```

`docs/STATUS.md` must state:

- current completed phase
- commands verified
- tests passing/failing
- measured results available
- known blockers
- next phase input contract

Do not leave architecture documentation describing functionality that the repository does not actually implement.

---

## 19. Standard Commands

Prefer repository-defined Make targets. Expected targets may include:

```bash
make install
make lint
make typecheck
make test
make collect-demo
make build-features
make extract-events-demo
make graph-upsert-demo
make train-baseline
make evaluate
make api
make web
make demo
```

Before claiming success, run the most relevant available commands rather than assuming they work.

If a target does not yet exist in the current phase, do not pretend that it does. Add it only when it can execute a meaningful, tested workflow.

---

## 20. Claude Code Workflow

### Before editing

1. Read this file, the active phase prompt, `README.md`, and relevant docs.
2. Inspect the repository instead of assuming its state.
3. Identify contract conflicts and temporal leakage risks.
4. State assumptions.
5. Propose a file-level implementation plan.
6. Define acceptance tests before implementation.

For cross-cutting changes, use Plan Mode first.

Use subagents only for separable work such as:

- read-only repository mapping
- test gap review
- independent security or leakage audit
- frontend accessibility review

Do not let multiple agents independently redefine core data contracts or edit the same files concurrently.

### During implementation

1. Implement only the requested phase.
2. Prefer the smallest complete vertical slice.
3. Preserve backward compatibility unless a migration is part of the phase.
4. Run focused tests after each logical change.
5. Keep fixture, replay, live, and research modes explicit.
6. Do not broaden scope merely because a library or service is available.
7. Do not commit, push, open a PR, or modify remote resources unless explicitly requested.

When ambiguity is non-blocking, choose the smallest reversible assumption and record it. Do not invent missing business results or data.

### After implementation

Run, as applicable:

```text
format
lint
typecheck
unit tests
integration tests
E2E tests
```

Then report:

1. changed files
2. commands executed
3. test results
4. acceptance criteria status
5. unresolved issues
6. data/API contract changes
7. next-phase input contract

Do not claim “complete” when required tests were not executed. State the exact limitation.

---

## 21. Phase Gates

Do not advance automatically to the next phase.

A phase is complete only when:

- its acceptance criteria are met
- relevant tests pass
- documentation reflects actual behavior
- measured outputs are real
- known limitations are recorded

Expected phase sequence:

```text
00 Contracts & Scaffold
01 Data Collection MVP
02 Demand Aggregation & Feature Store
03 LLM Event Extraction
04 Neo4j Graph Upsert
05 As-of Graph Feature Builder
06 Forecasting, Tuning & Evaluation
07 FastAPI & Next.js UI
08 Rebalancing & Quantum Research Mode
09 Final Audit & Portfolio Packaging
```

If a phase depends on an incomplete prior contract, stop implementation at the contract boundary, explain the inconsistency, and make the smallest corrective change needed.

---

## 22. Prohibited Patterns

Never do the following:

- use future data relative to `forecast_cutoff`
- use random split for the forecasting evaluation
- call inventory snapshot differences exact demand labels
- present fixture data as live
- fabricate news content, source evidence, model metrics, or API responses
- commit secrets or private keys
- make external network calls in unit tests
- silently swallow validation or collection errors
- store LLM output without schema validation
- accept an event without evidence spans
- generate explanations without provenance
- use Neo4j as decoration without feature generation
- claim causal effects from feature attribution
- claim quantum advantage
- present QAOA simulation as hardware execution
- hide failed trials or non-improving models
- weaken tests to satisfy a deadline
- perform broad refactors unrelated to the active phase

---

## 23. Definition of Portfolio-Ready

The repository is portfolio-ready only when a reviewer can reproduce the following from documented commands:

```text
fixture collection
→ demand aggregation
→ event extraction
→ graph upsert
→ as-of graph feature generation
→ baseline and event-aware forecasting
→ ablation evaluation
→ replay API and UI
→ scenario comparison
→ feasible rebalancing plan
```

The final package must clearly distinguish:

- real historical data
- curated fixtures
- optional live data
- measured experiment results
- research-only quantum functionality
- known limitations

The 90-second demo and README must match the actual implementation exactly.