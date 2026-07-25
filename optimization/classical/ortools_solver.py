"""Rebalancing solver via Google OR-Tools (`pywraplp` CBC) — same MILP, different engine.

`milp.py`가 ``scipy.optimize.milp``(HiGHS)로 푸는 것과 **동일한 정식화**를 OR-Tools로 푼다. 목적:
"OR-Tools로도 되나?"에 대한 답 — 같은 최적해가 나오는지 test로 검증(``ortools cost == milp cost ==
enumeration cost``). 정수 bike flow + 연속 shortage/overflow + asymmetric cost 그대로.

OR-Tools는 optional 의존이라 import는 함수 안에서 lazy하게 한다(없으면 명확한 오류). product 경로의
기본 solver는 여전히 scipy MILP이고, 이건 대체 backend로 검증·비교용이다.
"""

from __future__ import annotations

from .enumeration import enumerate_plans
from .objective import CostBreakdown, plan_cost
from .problem import Move, RebalancingPlan, RebalancingProblem


def ortools_plan(problem: RebalancingProblem) -> tuple[RebalancingPlan, CostBreakdown]:
    """Solve the rebalancing MILP with OR-Tools CBC. Falls back to the exact oracle on failure."""
    try:
        from ortools.linear_solver import pywraplp
    except ImportError as exc:  # optional dependency
        raise ImportError("ortools가 설치되어 있지 않습니다: pip install ortools") from exc

    n = len(problem.stations)
    pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
    if not pairs:
        plan = RebalancingPlan(moves=(), solver="ortools")
        return plan, plan_cost(problem, plan)

    bikes = [s.bikes for s in problem.stations]
    capacity = [s.capacity for s in problem.stations]
    target = [s.target for s in problem.stations]
    c = problem.costs
    V = problem.vehicle_capacity

    solver = pywraplp.Solver.CreateSolver("CBC")
    if solver is None:  # pragma: no cover - CBC always bundled
        raise RuntimeError("OR-Tools CBC backend unavailable")
    inf = solver.infinity()

    # integer bike flows x_ij (0..min(bikes_i, V)); continuous shortage s_i / overflow o_i (>=0)
    x = {(i, j): solver.IntVar(0, min(bikes[i], V), f"x_{i}_{j}") for (i, j) in pairs}
    s = [solver.NumVar(0, inf, f"s_{i}") for i in range(n)]
    o = [solver.NumVar(0, inf, f"o_{i}") for i in range(n)]

    for i in range(n):
        out_i = solver.Sum([x[(i, j)] for j in range(n) if j != i])
        in_i = solver.Sum([x[(j, i)] for j in range(n) if j != i])
        final_i = bikes[i] - out_i + in_i
        solver.Add(out_i <= bikes[i])            # 출발지 재고 초과 금지
        solver.Add(final_i >= 0)                 # 최종 재고 >= 0
        solver.Add(final_i <= capacity[i])       # 최종 재고 <= capacity
        solver.Add(s[i] >= target[i] - final_i)  # shortage = max(0, target - final)
        solver.Add(o[i] >= final_i - target[i])  # overflow = max(0, final - target)
    solver.Add(solver.Sum(list(x.values())) <= V)  # 차량 용량

    solver.Minimize(
        solver.Sum([c.distance_cost * problem.distance_km(i, j) * x[(i, j)] for (i, j) in pairs])
        + c.shortage_cost * solver.Sum(s)
        + c.overflow_cost * solver.Sum(o)
    )

    status = solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        # 해를 못 찾으면 조작하지 말고 exact oracle로 (sections 14.1, 22)
        return enumerate_plans(problem)

    moves = tuple(
        Move(
            origin_id=problem.stations[i].station_id,
            destination_id=problem.stations[j].station_id,
            quantity=int(round(x[(i, j)].solution_value())),
            distance_km=round(problem.distance_km(i, j), 4),
        )
        for (i, j) in pairs
        if round(x[(i, j)].solution_value()) > 0
    )
    plan = RebalancingPlan(moves=moves, solver="ortools")
    return plan, plan_cost(problem, plan)
