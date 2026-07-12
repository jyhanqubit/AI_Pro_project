# ShockFlow AI — Product Requirements (as built)

Event-aware urban mobility **demand forecasting** and **fleet rebalancing** decision support.
This document describes what the repository actually implements; the operating contract is
[CLAUDE.md](../CLAUDE.md).

## Problem

Bike-share demand has a predictable diurnal/weekly rhythm plus **irregular shocks** driven by
events (transit disruptions, venue events, weather, closures). Operators need to (a) see a shock
coming, (b) understand *why* the forecast changed, (c) test a counterfactual, and (d) turn it
into a concrete rebalancing action — fast.

## Product claim (and its limits)

> ShockFlow AI detects irregular demand shocks from timestamped events, converts them into
> traceable graph features, quantifies their **model-attributed** forecast impact, and turns the
> forecast into an operational action.

"Model-attributed", not causal (§4). On the current evaluation window the *measured* event lift
is null because the curated events postdate the trip data — stated plainly in
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md); fabricating overlapping events is prohibited (§22).

## Canonical flow

```
Citi Bike demand history + timestamped news/events + current station inventory
 → LLM event extraction → event graph → as-of numeric graph features
 → H3 zone-hour demand forecast → explanation & scenario comparison → feasible rebalancing plan
```

## Users & primary flow

Operations dispatcher / planner. The UI follows **Alert → Why → Simulate → Act**:

1. **Control Tower** — zone risk overview, replay clock, event alerts, baseline vs event-aware
   forecast.
2. **Why Changed** — evidence article → event → H3 zone → feature trace + model-attributed delta.
3. **Scenario Lab** — toggle events on/off and compare forecasts.
4. **Rebalancing Planner** — origin/destination/quantity/distance, explicit feasibility, shortage
   reduction.

## Scope (MVP)

Three primary sources: Citi Bike trip history (batch labels), a curated demo news fixture (JSONL,
replayed by `available_at`), and GBFS `station_status` (inventory). Everything else (GDELT, MTA,
weather, Kafka, Airflow, live quantum hardware) is an explicitly-deferred optional extension (§2).

## Operating modes

`demo_fixture`, `historical_replay`, `live`, `research`. **Demo Mode works with no API keys,
fully offline.** Historical Replay is the presentation mode; live collectors are opt-in and off by
default; Research Mode (QUBO/QAOA) never feeds Demo/Replay/Live (§3).

## Functional requirements (implemented)

- Temporally-correct, leakage-safe features at the **H3 zone × local hour** grain; targets
  `departures`, `arrivals`, `net_flow` (§4, §5).
- Deterministic mock LLM extraction with evidence spans and schema validation (§8).
- Idempotent event graph feeding **numeric** graph features (§9, §10).
- Forecasting ladder (seasonal-naive → tree baseline → event-aware) with rolling-origin
  evaluation, a B0–B4 ablation, and WAPE/MAE/MASE/event-window/peak-direction/delta-stability plus
  the domain OCS metric (§11).
- Offline replay API and operator UI (§12, §13).
- Classical rebalancing (greedy + MILP + exact) with explicit feasibility, and a validated
  research-only QUBO/QAOA track (§14).

## Non-goals

Multi-vehicle routing, road-network distances, online retraining, live quantum hardware, and
causal identification are out of scope for the MVP.

## Definition of portfolio-ready (§23)

A reviewer can reproduce, from documented commands: fixture collection → demand aggregation →
event extraction → graph upsert → as-of graph features → baseline & event-aware forecasting →
ablation → replay API & UI → scenario comparison → feasible rebalancing plan. Real data, curated
fixtures, optional live data, measured results, research-only quantum, and known limitations are
clearly separated.
