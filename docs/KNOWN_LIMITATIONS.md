# Known Limitations

Scope boundaries (CLAUDE.md §11.4, §18, §22). Nothing here is hidden to make a phase
look complete.

## Data

- **Single month, single system area.** The forecasting evaluation uses real Citi Bike JC trip
  history for **June 2026 only** (~110k trips → ~40k demand cells → ~31k usable feature rows
  after the one-week warm-up). That is enough for a rolling-origin demonstration but thin for
  strong seasonal claims. The raw file is git-ignored (§7.1); a small sample fixture is
  versioned for tests.
- **News and GBFS remain fixtures.** The curated news fixture and the GBFS station-status
  fixture are the default inputs; live collectors are opt-in and disabled by default.

## Event-aware forecasting (the central caveat)

- **Event lift is not demonstrable on the June window.** The only curated events are dated
  2026-07-12, which is *after* the June trip data. The availability rule (§5.2) therefore forces
  every event/graph feature to zero across the whole evaluation window, so ablation levels
  **B2–B4 collapse onto B1**. The runner verifies this (zero graph snapshots at the last
  cutoff) rather than assuming it. A genuine event-lift measurement requires an evaluation span
  that overlaps curated events; producing one would mean sourcing real, provenance-bearing news
  for the trip window — **fabricating events is prohibited (§22)** and has not been done.
- What *is* validated: the as-of feature machinery and its leakage boundary
  (`tests/unit/test_graph_features.py`, incl. the 14:01→14:00 regression). The graph → numeric
  feature path is real; only its *predictive contribution on this particular window* is null.

## Modelling

- **1-hour-ahead only.** The current setup forecasts the target hour from information known at
  its start. Longer horizons are not yet implemented.
- **Point forecasts, no calibrated intervals.** Per §6.5, p10/p50/p90 are omitted rather than
  invented.
- **Global model.** One model across all zones; zone identity enters only through demand-scale
  features (expanding/rolling means), not as an explicit fixed effect.

## Rebalancing (Phase 08)

- **Static, single-vehicle, single-period.** The optimizer plans one relocation round toward the
  as-of targets with one move budget (`vehicle_capacity`). It is not a routed multi-vehicle tour
  and has no inter-period dynamics; distance is straight-line (`haversine_km`), not road network.
- **Targets are a labelled demo heuristic.** Station targets are `base_target` (from the curated
  fixture) plus the event-aware `demo-heuristic-v1` forecast delta in the zone — not the measured
  Phase 06 model. The station inventory is a curated fixture, not live GBFS.
- **Small instance.** The demo has five stations; MILP (`scipy.optimize.milp`) and the exact
  enumeration oracle agree on the optimum at this scale. Enumeration is guarded and only usable on
  small instances.

## Quantum Research Mode (Phase 08)

- **Research only; simulator, never hardware; no advantage claim.** QUBO/QAOA outputs never feed
  Demo, Historical Replay, or Live views (§3). No quantum-advantage claim is made.
- **Quadratic surrogate, small scale.** The QUBO encodes a *quadratic imbalance surrogate* of the
  operational (asymmetric L1) objective, validated against exact enumeration (encoding matches for
  every bit vector; QUBO optimum == enumeration optimum). The operator plan always comes from the
  classical solvers.
- **QAOA is optional and unverified here.** `qiskit` is not installed in this environment, so the
  QAOA path returns "unavailable" and its test is skipped with a documented reason. When installed,
  the sampled optimum is checked against the exact QUBO ground state.

## Environment

- Local `.venv` runs Python 3.12.10 (repo pins `>=3.11`; the machine lacks 3.11). The web CI/build
  was verified under Node 22 (`npm run typecheck` and `npm run build` pass).
- Console output is ASCII-only for Windows cp949 compatibility.
