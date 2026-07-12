# ShockFlow AI

Event-aware urban mobility demand forecasting and fleet rebalancing decision-support system.

ShockFlow AI detects irregular demand shocks from timestamped events, converts them into
traceable graph features, quantifies their **model-attributed** forecast impact (not proven
causality), and turns the forecast into an operational rebalancing action.

```text
Citi Bike demand history
+ timestamped news / event input
+ current station inventory
→ LLM event extraction → Neo4j event graph → as-of numeric graph features
→ H3 zone-hour demand forecast → explanation & scenario comparison → feasible rebalancing plan
```

The operating contract for all development lives in [CLAUDE.md](CLAUDE.md).

## Operating modes

Every record, response, and view declares its mode: `demo_fixture`, `historical_replay`,
`live`, or `research`. **Demo Mode runs fully offline, with no external API keys.**

## Getting started

```bash
make install       # create .venv and install the package (editable) + dev tools
make lint          # ruff check + format check
make typecheck     # mypy
make test          # pytest
make collect-demo    # run all three fixture collectors offline and print a summary
make build-features  # aggregate demand (H3 zone x local hour) + leakage-safe features
make extract-events-demo  # extract events from the news fixture (deterministic mock LLM)
make graph-upsert-demo    # upsert events into the offline event graph (idempotent)
```

> On Windows without `make`, run the equivalent commands directly, e.g.
> `python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"`.

Copy `.env.example` to `.env` before running; the defaults are safe and offline-compatible.

## Repository layout

| Path | Purpose |
|------|---------|
| `contracts/` | Typed Pydantic v2 data contracts shared across boundaries (§6) |
| `services/api/` | FastAPI service (Phase 07) |
| `pipelines/collectors/` | Data collectors: Citi Bike, news fixture, GBFS |
| `pipelines/events/` | LLM event extraction |
| `pipelines/features/` | Demand aggregation (H3 zone x local hour) + leakage-safe features |
| `ml/forecasting/` | Baseline and event-aware forecasting models |
| `optimization/classical/` | Greedy / MILP rebalancing |
| `optimization/quantum/` | QUBO / QAOA research mode |
| `apps/web/` | Next.js operator UI (Phase 07) |
| `config/` | Typed runtime configuration |
| `data/fixtures/` | Curated, versioned demo fixtures |
| `data/raw/`, `data/processed/` | Local inputs / artifacts (git-ignored) |
| `docs/` | PRD, architecture, contracts, evaluation, status |
| `tests/` | `unit/`, `integration/`, `e2e/` |

## Status

See [docs/STATUS.md](docs/STATUS.md) for the current phase, verified commands, and blockers.
