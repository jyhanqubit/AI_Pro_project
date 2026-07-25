# Rebalancing & Quantum Research Mode (Phase 08)

Turns the event-aware forecast into a feasible fleet-rebalancing plan — the **Act** step of the
`Alert → Why → Simulate → Act` flow (CLAUDE.md §13, §14). Classical solvers produce the
operator-facing plan; a small QUBO/QAOA track is **research only** and never feeds Demo,
Historical Replay, or Live views (§3).

## Problem

Given a set of dock stations, each with current bikes, total capacity, and a desired **target**
inventory, move an integer number of bikes between stations to best meet the targets under a
single-vehicle move budget.

Data model (`optimization/classical/problem.py`):

- `Station(station_id, name, lat, lng, bikes, capacity, target, zone_id)` with invariants
  `0 ≤ bikes ≤ capacity` and `0 ≤ target ≤ capacity`.
- `Move(origin_id, destination_id, quantity, distance_km)` — great-circle km via the shared
  `haversine_km` kernel.
- `RebalancingProblem(stations, costs, vehicle_capacity)`, `RebalancingPlan(moves, solver)`.

Where the demo targets come from: the curated fixture `data/fixtures/rebalancing_demo.json` gives
each station a normal-hour `base_target`. The API (`services/api/rebalancing.py`) raises the
target in event-exposed H3 zones by the **event-aware demo-heuristic forecast delta** as-of the
replay cutoff — a transparent, clearly-labelled heuristic (`demo-heuristic-v1`, Historical
Replay), **not** the measured Phase 06 model (§22). Before events are available, targets equal
the base and the plan is empty; once the transit / venue events land, the event zones go into
deficit and the solver moves bikes in.

## Objective (§14.1)

Asymmetric operational cost over the post-plan inventory `f_i` (`optimization/classical/objective.py`,
weights in `config/rebalancing.py`):

```
cost = shortage_cost · Σ_i max(0, target_i − f_i)     # unmet demand (a stockout loses a trip)
     + overflow_cost · Σ_i max(0, f_i − target_i)     # over-supply (wasted bikes / blocked docks)
     + distance_cost · Σ_moves distance_km · quantity # relocation effort
```

Shortage is weighted above overflow (default 3 : 1), mirroring the asymmetric Phase 06 metric
(OCS, `docs/EVALUATION_PROTOCOL.md`). The function is pure and total — it scores any plan,
feasible or not — so every solver is compared on one scale.

## Feasibility (§14.1)

`optimization/classical/feasibility.py` checks a plan explicitly and reports violations in plain
text (never silently repaired):

- quantities are positive integers, origin ≠ destination;
- a station cannot send more bikes than it has (`outflow ≤ bikes`);
- a station cannot exceed capacity on receipt (`final ≤ capacity`);
- final inventory is non-negative;
- total moved bikes respect `vehicle_capacity`.

A plan is only surfaced through the API/UI after this passes.

## Solver ladder (§14.1)

1. **Greedy** (`greedy.py`) — repeatedly moves bikes from the surplus station to the deficit
   station with the highest marginal gain (`shortage_cost + overflow_cost − distance_cost·d`)
   until no positive-gain move remains or the vehicle is full. Always feasible; never worse than
   doing nothing. Not guaranteed optimal — the honest lower bar.
2. **MILP** (`milp.py`) — the exact optimum via `scipy.optimize.milp` (HiGHS). Integer flows
   `x_ij` between every ordered pair, with linearised shortage/overflow variables `s_i, o_i`; at
   the optimum they equal `max(0, target−f)` / `max(0, f−target)` because both carry positive
   cost, so the LP objective equals `objective.plan_cost`. A solver failure degrades to the exact
   enumeration oracle rather than fabricating a plan.
3. **Enumeration oracle** (`enumeration.py`) — brute-forces the optimum over small instances
   (restricted, objective-preservingly, to surplus→deficit edges) and is the independent
   correctness check for the MILP and QUBO. Guarded by a search-space cap.
4. **OR-Tools backend** (`ortools_solver.py`, optional `pip install -e ".[ortools]"`) — the same
   MILP formulation solved with Google OR-Tools (`pywraplp`, CBC) instead of SciPy/HiGHS. This is
   an *alternative engine*, not the default: the product path stays on `scipy.optimize.milp`.
   `tests/unit/test_v2_ortools_solver.py` validates **OR-Tools cost == MILP cost == enumeration
   cost** across instances (all reach the same optimum) and that its plans are feasible. If
   `ortools` is absent the test skips (no fake result).

Validated relationships (`tests/unit/test_rebalancing.py`): greedy is always feasible and ≤
do-nothing; **MILP cost == enumeration cost** (optimal) and ≤ greedy; a binding vehicle capacity
is respected. The OR-Tools backend matches all three (`test_v2_ortools_solver.py`).

## Quantum Research Mode (§14.2) — research only

`optimization/quantum/qubo.py` maps a **small** instance to a QUBO for QAOA.

**Variable mapping.** Pick a small set of directed edges; each carries an integer flow
`x_e ∈ [0, U_e]`, binary-encoded with bounded coefficients `w_e = [1, 2, 4, …, r]` so the subset
sums cover exactly `[0, U_e]`. Final inventory `f_i = bikes_i − Σ_{origin} x_e + Σ_{dest} x_e`.

**Energy (surrogate).**

```
E(x) = imbalance_weight · Σ_i (f_i − target_i)²  +  distance_cost · Σ_e d_e · x_e
```

This is a **quadratic imbalance surrogate** of the operational (asymmetric L1) objective. Edge
bounds are chosen so every point in the encoding box is feasible, so no penalty terms are needed
and the QUBO optimum is directly comparable to exact enumeration of the same energy.

**Validation (required, §14.1 step 4 / §14.2).** `tests/unit/test_qubo.py` asserts:

- the Q-matrix energy equals the surrogate energy for **every** binary assignment (encoding is
  correct);
- **QUBO brute-force optimum == exact enumeration optimum** of the surrogate;
- on a crafted instance where the surrogate and the operational objective agree, the QUBO optimum
  plan coincides with the **classical MILP** plan.

**QAOA** (`qaoa.py`) is optional. `qiskit` is imported lazily; if absent, `solve_qaoa` returns an
explicit "unavailable" result and its test is skipped with a documented reason. When present, the
sampled optimum is checked against the exact QUBO ground state. Results are **simulator** results,
never presented as hardware, and **no quantum-advantage claim is made** (§14.2).

## API & UI

- `POST /v1/rebalancing/solve` (`services/api/app.py`, schemas in `schemas.py`) — body
  `{cutoff?, method: "greedy"|"milp", vehicle_capacity?}`. Returns the mode, cutoff, method,
  feasibility (+ reason if infeasible), the moves, per-station before→after inventory, and
  shortage/overflow reduction vs the do-nothing baseline. Out-of-window cutoffs return `400`.
- `apps/web/app/rebalancing/page.tsx` renders the plan: feasibility badge, moves table,
  station inventory before→after, and the cost/shortage summary.

## Run it

```bash
make rebalance-demo          # python -m optimization.demo — greedy, MILP, exact, QUBO validation
make api                     # then POST /v1/rebalancing/solve
```
