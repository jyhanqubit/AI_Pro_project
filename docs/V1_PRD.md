# ShockFlow AI V1 — Product Requirements

> Status: **V1-00 (contracts & scaffold) implemented.** Everything below marked _(planned)_ is a
> contract/skeleton only — not yet a working endpoint (V1_Prompt §6 acceptance: do not document
> unbuilt endpoints as built).

## 1. What V1 adds over v0

v0 delivers the offline vertical slice: event extraction → graph → as-of features →
demo-heuristic forecast → rebalancing. V1 turns the **demo heuristic into measured models** and adds
a **rider-facing recommendation + incentive** layer, **anomaly detection**, a **live-shadow**
pipeline, and **experimentation**, each behind an explicit claim boundary.

## 2. Users & jobs

- **Rider** — "어디서 빌리고/반납할까?" → context-aware RENT/RETURN station recommendation _(planned)_.
- **Operator** — forecast, anomalies, rebalancing, incentive/policy simulation _(planned)_.
- **Analyst** — event-lift evaluation and (simulated) experiments _(planned)_.

## 3. Core claim (unchanged discipline)

V1 quantifies **model-attributed** event impact (M1 vs M1-zero), never causal impact. Recommendation
uplift and policy effects are **simulated** until a real randomized experiment with real users exists.

## 4. Operating modes (V1_Prompt §6)

`demo_fixture · historical_replay · live_shadow · policy_simulation · experiment_dry_run · research`.
Demo/offline-safe by default; live collectors disabled; a live failure never breaks Demo/Replay.

## 5. Claim states (the boundary)

Every predicted/serving artifact carries `measured | pending | simulated | dry_run | research`
(`contracts/v1/enums.py::ClaimState`). See `docs/V1_CLAIMS_MATRIX.md`.

## 6. Scope guards

- No fabricated metrics/latency/uplift; only real executed runs produce numbers.
- GBFS inventory deltas are never demand labels.
- Random splits are forbidden for temporal/recommendation evaluation.
- No personalised collaborative filtering; recommendation is context-aware station ranking.
- Research-mode (QUBO/QAOA) outputs never feed serving views.

## 7. Planned endpoints _(contract-only in V1-00)_

`POST /v1/recommendations/stations`, `POST /v1/recommendations/compare-event-impact` — defined in
`docs/V1_ARCHITECTURE.md` as planned; implemented in V1-07C.
