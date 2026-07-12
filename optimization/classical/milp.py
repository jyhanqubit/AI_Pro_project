"""Exact constrained rebalancing via MILP. CLAUDE.md section 14.1 (build order step 2).

Formulates the asymmetric operational objective as a mixed-integer linear program and solves it
with ``scipy.optimize.milp`` (HiGHS). Integer bike flows ``x_ij`` between every ordered station
pair, with linearised shortage/overflow deviations:

    minimise  distance_cost * sum_ij d_ij x_ij
              + shortage_cost * sum_i s_i + overflow_cost * sum_i o_i
    s.t.      out_i = sum_j x_ij,  in_i = sum_j x_ji,  f_i = bikes_i - out_i + in_i
              out_i <= bikes_i                          (cannot move more than available)
              0 <= f_i <= capacity_i                    (floor & destination capacity)
              sum_ij x_ij <= vehicle_capacity           (one truck tour)
              s_i >= target_i - f_i,  s_i >= 0          (shortage lower bound)
              o_i >= f_i - target_i,  o_i >= 0          (overflow lower bound)
              x_ij integer >= 0

At the optimum ``s_i = max(0, target_i - f_i)`` and ``o_i = max(0, f_i - target_i)`` because both
carry positive cost, so the LP objective equals the operational objective in
``objective.plan_cost``. For instances too small or degenerate the solver still returns the exact
optimum; a solver failure falls back to the enumeration oracle.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from .enumeration import enumerate_plans
from .objective import CostBreakdown, plan_cost
from .problem import Move, RebalancingPlan, RebalancingProblem


def milp_plan(problem: RebalancingProblem) -> tuple[RebalancingPlan, CostBreakdown]:
    n = len(problem.stations)
    pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
    np_ = len(pairs)
    if np_ == 0:
        plan = RebalancingPlan(moves=(), solver="milp")
        return plan, plan_cost(problem, plan)

    bikes = np.array([s.bikes for s in problem.stations], dtype=float)
    capacity = np.array([s.capacity for s in problem.stations], dtype=float)
    target = np.array([s.target for s in problem.stations], dtype=float)
    c = problem.costs

    # Variable layout: [x_0..x_{np-1}] [s_0..s_{n-1}] [o_0..o_{n-1}]
    n_vars = np_ + 2 * n
    s_off, o_off = np_, np_ + n

    # Objective.
    cost_vec = np.zeros(n_vars)
    for p, (i, j) in enumerate(pairs):
        cost_vec[p] = c.distance_cost * problem.distance_km(i, j)
    cost_vec[s_off : s_off + n] = c.shortage_cost
    cost_vec[o_off : o_off + n] = c.overflow_cost

    # Bounds: 0 <= x_p <= min(bikes_origin, vehicle_capacity); s,o >= 0.
    lb = np.zeros(n_vars)
    ub = np.full(n_vars, np.inf)
    for p, (i, _) in enumerate(pairs):
        ub[p] = min(bikes[i], problem.vehicle_capacity)

    integrality = np.zeros(n_vars)
    integrality[:np_] = 1  # integer bike flows

    rows: list[np.ndarray] = []
    con_lb: list[float] = []
    con_ub: list[float] = []

    for i in range(n):
        origin_ps = [p for p, (a, _) in enumerate(pairs) if a == i]
        dest_ps = [p for p, (_, b) in enumerate(pairs) if b == i]

        # (1) outflow_i <= bikes_i
        row = np.zeros(n_vars)
        row[origin_ps] = 1.0
        rows.append(row)
        con_lb.append(-np.inf)
        con_ub.append(bikes[i])

        # (2) floor & capacity: -bikes_i <= -out_i + in_i <= capacity_i - bikes_i
        row = np.zeros(n_vars)
        row[origin_ps] = -1.0
        row[dest_ps] = 1.0
        rows.append(row)
        con_lb.append(-bikes[i])
        con_ub.append(capacity[i] - bikes[i])

        # (3) shortage: s_i - out_i + in_i >= target_i - bikes_i
        row = np.zeros(n_vars)
        row[s_off + i] = 1.0
        row[origin_ps] = -1.0
        row[dest_ps] = 1.0
        rows.append(row)
        con_lb.append(target[i] - bikes[i])
        con_ub.append(np.inf)

        # (4) overflow: o_i + out_i - in_i >= bikes_i - target_i
        row = np.zeros(n_vars)
        row[o_off + i] = 1.0
        row[origin_ps] = 1.0
        row[dest_ps] = -1.0
        rows.append(row)
        con_lb.append(bikes[i] - target[i])
        con_ub.append(np.inf)

    # (5) vehicle capacity: sum x <= V
    row = np.zeros(n_vars)
    row[:np_] = 1.0
    rows.append(row)
    con_lb.append(-np.inf)
    con_ub.append(float(problem.vehicle_capacity))

    constraints = LinearConstraint(np.vstack(rows), np.array(con_lb), np.array(con_ub))
    res = milp(
        c=cost_vec,
        constraints=constraints,
        integrality=integrality,
        bounds=Bounds(lb, ub),
    )

    if not res.success or res.x is None:
        # Degrade to the exact oracle rather than fabricate a plan (sections 14.1, 22).
        return enumerate_plans(problem)

    x = np.rint(res.x[:np_]).astype(int)
    moves = tuple(
        Move(
            origin_id=problem.stations[i].station_id,
            destination_id=problem.stations[j].station_id,
            quantity=int(q),
            distance_km=round(problem.distance_km(i, j), 4),
        )
        for (i, j), q in zip(pairs, x, strict=True)
        if q > 0
    )
    plan = RebalancingPlan(moves=moves, solver="milp")
    return plan, plan_cost(problem, plan)
