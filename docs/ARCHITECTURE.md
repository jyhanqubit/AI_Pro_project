# Architecture (as built)

A single Python package set plus a Next.js frontend. Everything on the golden path runs offline
from fixtures; external collectors and databases are optional and behind flags (CLAUDE.md §2, §3).

## Layers & data flow

```
                 data/fixtures (news JSONL, GBFS JSON, trip CSV, rebalancing JSON)
                          │
pipelines/collectors  ────┤  Collector interface (fixture mode mandatory, live opt-in)
   ├─ citibike (CSV/ZIP)  │      → contracts.TripRecord / ArticleRecord / StationStatusRecord
   ├─ news (JSONL)        │
   └─ gbfs (station_status)
                          ▼
pipelines/features/aggregate + lags + calendar + temporal
   trips → DemandCell (H3 zone × local hour) → leakage-safe demand features
                          │
pipelines/events (mock LLM provider) ── ArticleRecord → EventExtraction (evidence-grounded)
                          ▼
pipelines/graph (offline in-memory or Neo4j) ── Article→Event→Place→H3Zone→(Station)
                          ▼
pipelines/features/graph_features ── as-of FeatureSnapshot per zone (available_at ≤ cutoff)
                          ▼
ml/forecasting ── seasonal-naive B0 → model zoo → event-aware; rolling-origin CV; B0–B4; metrics+OCS
                          │
services/api (FastAPI, offline ReplayEngine)  ◄── config/api demo heuristic (demo-heuristic-v1)
   /v1/health /replay/* /events /forecasts /zones/{id}/explanation /scenarios /rebalancing/solve
                          │                                   │
                          ▼                                   ▼
apps/web (Next.js)                        optimization/classical (greedy, MILP, exact)
   Control Tower / Why / Scenario / Rebalancing   optimization/quantum (QUBO, optional QAOA)
```

## Key design decisions

- **Contracts at boundaries** (`contracts/`, Pydantic v2, `extra="forbid"`) — trip, article,
  event, demand, feature, forecast, station. Contract drift fails loudly.
- **Temporal correctness first** (§5). Canonical timestamps in UTC; trips localized to
  `America/New_York` with explicit DST handling before hourly aggregation. Event availability is
  `available_at = max(published_at, first_seen_at)`, used only when `≤ forecast_cutoff`. Leakage
  regression tests are load-bearing and never weakened.
- **Provider interfaces + deterministic mocks** — LLM extraction (`MockLlmProvider`) and
  collectors have fixture modes so Demo Mode and tests need no network or keys.
- **Graph is not decoration** (§9) — the event graph exists to produce numeric, versioned,
  as-of graph features; an integration test proves idempotent replay does not inflate node counts.
- **Pure kernels** — geographic/temporal decay (`pipelines/features/kernels.py`) and the
  rebalancing objective/feasibility are small pure functions, trivially unit-testable.
- **Demo heuristic vs measured model** — the API/UI forecast is a transparent, separately-versioned
  heuristic (`demo-heuristic-v1`); the measured Phase 06 leaderboard is a different artifact. They
  are never conflated (§13, §22).
- **Research isolation** — QUBO/QAOA live under `optimization/quantum/` and never feed the
  operator plan or any Demo/Replay/Live view (§3).

## Configuration

Typed modules under `config/` (features, events, graph_features, forecasting, api, collectors,
places, rebalancing, settings). Search spaces and domain parameters live here, not in notebooks,
so results are reproducible from configuration. `.env.example` documents variables; demo defaults
are offline-safe (`SHOCKFLOW_MODE=demo_fixture`, live flags off, `LLM_PROVIDER=mock`).

## Testing (§17)

Unit (timestamps/DST, trip normalization, lag/rolling leakage, event schema/evidence/dedup, as-of
filtering, graph kernels, metrics, optimizer feasibility, QUBO validation), integration (fixture
collection, Neo4j constraints/idempotency, feature provenance, API schema + rebalancing),
end-to-end golden path (13:59 boundary → 14:00 event → graph → feature → forecast → explanation →
scenario toggle → feasible plan). No test touches the public internet.

## Deployment shape

`make api` runs the offline FastAPI service; `make web` runs the Next.js dev server. No managed
cloud services are required for the demo. Large raw data, model binaries, secrets, and local DB
volumes are git-ignored (§15).
