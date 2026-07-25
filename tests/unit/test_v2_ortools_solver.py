"""OR-Tools 배치 solver — scipy MILP·완전열거와 '같은 최적해'인지 검증.

핵심 주장: "OR-Tools로도 된다"를 말이 아니라 test로 — 여러 소규모 instance에서
ortools total_cost == milp total_cost == enumeration total_cost (모두 최적이므로 일치)이고,
OR-Tools 해가 feasibility 검사를 통과함을 확인한다.
"""

from __future__ import annotations

import pytest

from optimization.classical.enumeration import enumerate_plans
from optimization.classical.feasibility import check_feasibility
from optimization.classical.milp import milp_plan
from optimization.classical.problem import RebalancingProblem, Station

ortools = pytest.importorskip("ortools", reason="ortools 미설치 시 skip")
from optimization.classical.ortools_solver import ortools_plan  # noqa: E402


def _problem(spec, vehicle_capacity=18):
    # spec: [(bikes, capacity, target), ...] — 좌표는 소규모 격자로 배치
    stations = tuple(
        Station(station_id=f"S{i}", name=f"S{i}", lat=40.70 + 0.01 * i, lng=-74.00 + 0.01 * i,
                bikes=b, capacity=cap, target=t)
        for i, (b, cap, t) in enumerate(spec)
    )
    return RebalancingProblem(stations=stations, vehicle_capacity=vehicle_capacity)


CASES = [
    [(10, 20, 5), (0, 20, 8), (18, 20, 6)],       # 과잉→부족 재배치 필요
    [(5, 10, 5), (5, 10, 5)],                       # 이미 균형 → 이동 0이 최적
    [(20, 20, 2), (0, 20, 18)],                     # 강한 편향
    [(3, 12, 9), (11, 12, 4), (7, 12, 7), (0, 12, 6)],
]


@pytest.mark.parametrize("spec", CASES)
def test_ortools_matches_milp_and_enumeration(spec):
    prob = _problem(spec)
    _, or_cost = ortools_plan(prob)
    _, milp_cost = milp_plan(prob)
    _, enum_cost = enumerate_plans(prob)
    # 세 solver 모두 같은 최적 total_cost (부동소수 오차 허용)
    assert or_cost.total_cost == pytest.approx(enum_cost.total_cost, abs=1e-6)
    assert milp_cost.total_cost == pytest.approx(enum_cost.total_cost, abs=1e-6)


@pytest.mark.parametrize("spec", CASES)
def test_ortools_plan_is_feasible(spec):
    prob = _problem(spec)
    plan, _ = ortools_plan(prob)
    assert check_feasibility(prob, plan).feasible
    assert plan.solver == "ortools"
