"""Offline rebalancing demo. CLAUDE.md sections 14, 19.

Runs the golden-path "Act" step end-to-end from fixtures: builds the as-of rebalancing problem
at a post-event cutoff (targets raised by the event-aware demo-heuristic forecast), solves it
greedily and with the MILP, verifies feasibility, then validates a small QUBO against exact
enumeration (Quantum Research Mode). Prints a human summary; no network, no API key.

    python -m optimization.demo
"""

from __future__ import annotations

from datetime import datetime

from optimization.classical.enumeration import bounded_subproblem, enumerate_plans
from optimization.classical.milp import milp_plan
from optimization.quantum.qubo import (
    brute_force_qubo,
    build_qubo,
    enumerate_surrogate_optimum,
    qubo_plan,
)
from services.api.rebalancing import build_problem, solve
from services.api.replay import ReplayEngine

POST_EVENT_CUTOFF = datetime.fromisoformat("2026-07-12T15:30:00-04:00")


def main() -> None:
    engine = ReplayEngine()

    print("== ShockFlow AI — rebalancing demo (Historical Replay, offline) ==")
    print(f"cutoff: {POST_EVENT_CUTOFF.isoformat()}  (both events available)\n")

    for method in ("greedy", "milp"):
        sol = solve(engine, POST_EVENT_CUTOFF, method=method)
        print(
            f"[{method:6}] feasible={sol.feasible}  moved={sol.plan.total_moved} bikes  "
            f"cost {sol.baseline_cost.total_cost} -> {sol.cost.total_cost}  "
            f"shortage {sol.baseline_cost.shortage_units} -> {sol.cost.shortage_units}"
        )
        for m in sol.plan.moves:
            print(
                f"           move {m.origin_id} -> {m.destination_id}: {m.quantity} "
                f"({m.distance_km:.2f} km)"
            )

    # Exact oracle cross-checks the MILP. Full-scale exact enumeration is intractable (that is the
    # whole point of the MILP, §14.1), so both solvers run on a small, tractable slice of the
    # problem — the largest surplus/deficit stations with a bounded vehicle capacity.
    problem, _ = build_problem(engine, POST_EVENT_CUTOFF)
    sub = bounded_subproblem(problem)
    _, sub_milp_cost = milp_plan(sub)
    _, exact_cost = enumerate_plans(sub)
    match = sub_milp_cost.total_cost == exact_cost.total_cost
    print(
        f"\n[exact ] validation slice: {len(sub.stations)} stations, "
        f"vehicle_cap={sub.vehicle_capacity}"
    )
    print(
        f"[exact ] MILP cost {sub_milp_cost.total_cost} vs exact enumeration "
        f"{exact_cost.total_cost}  -> match: {match}"
    )

    # --- Quantum Research Mode: small QUBO validated against exact enumeration --------------
    print("\n== Quantum Research Mode (QUBO) — research only; simulator, no advantage claim ==")
    # A single surplus->deficit edge (Grove St -> Hoboken Terminal).
    stations = problem.stations
    try:
        gi = problem.index_of("JC_GROVE")
        hi = problem.index_of("JC_HOBOKEN")
    except KeyError:
        print("demo stations not found; skipping QUBO demo")
        return
    upper = min(stations[gi].surplus, stations[hi].deficit, problem.vehicle_capacity)
    qubo = build_qubo(problem, [(gi, hi)], [upper], imbalance_weight=10.0)
    _, q_energy = brute_force_qubo(qubo)
    _, e_energy = enumerate_surrogate_optimum(problem, [(gi, hi)], [upper], imbalance_weight=10.0)
    qplan = qubo_plan(qubo, problem)
    print(f"edge Grove St -> Hoboken Terminal, x in [0, {upper}], {qubo.num_vars} qubits")
    print(f"QUBO brute-force energy = {q_energy:.4f}   exact enumeration energy = {e_energy:.4f}")
    print(f"match: {abs(q_energy - e_energy) < 1e-9}   decoded move = {qplan.total_moved} bikes")


if __name__ == "__main__":
    main()
