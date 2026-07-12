"""Unit tests for Quantum Research Mode. CLAUDE.md sections 14.2, 17.

Validates the QUBO encoding against exact enumeration (required), confirms the QUBO optimum
coincides with the classical operational optimum on a crafted instance, and checks the QAOA path
degrades cleanly (skipping with a documented reason when qiskit is absent). No quantum-advantage
claim; simulator results are never treated as hardware.
"""

from __future__ import annotations

from itertools import product

import pytest

from optimization.classical.milp import milp_plan
from optimization.classical.problem import RebalancingProblem, Station
from optimization.quantum.qaoa import QaoaResult, qiskit_available, solve_qaoa
from optimization.quantum.qubo import (
    bounded_binary_weights,
    brute_force_qubo,
    build_qubo,
    enumerate_surrogate_optimum,
    qubo_plan,
    surrogate_energy,
)

IMB = 10.0


def _matched_instance() -> tuple[RebalancingProblem, list[tuple[int, int]], list[int]]:
    """Single-edge instance where surplus == deficit, so the surrogate optimum moves them all."""
    stations = (
        Station("GRV", "Grove St", 40.7196, -74.0431, bikes=12, capacity=20, target=6),  # surplus 6
        Station(
            "HOB", "Hoboken Terminal", 40.7360, -74.0301, bikes=2, capacity=20, target=8
        ),  # deficit 6
    )
    p = RebalancingProblem(stations=stations, vehicle_capacity=18)
    edges = [(0, 1)]
    bounds = [min(6, 6, 18)]
    return p, edges, bounds


def test_bounded_binary_weights_cover_range_exactly() -> None:
    for u in range(0, 12):
        weights = bounded_binary_weights(u)
        reachable = {
            sum(w for w, b in zip(weights, bits, strict=True) if b)
            for bits in product((0, 1), repeat=len(weights))
        }
        assert reachable == set(range(u + 1))  # covers [0, u], nothing above


def test_qubo_encoding_matches_surrogate_energy() -> None:
    p, edges, bounds = _matched_instance()
    qubo = build_qubo(p, edges, bounds, imbalance_weight=IMB)
    for bits in product((0, 1), repeat=qubo.num_vars):
        q = qubo.decode_quantities(bits)
        assert qubo.energy(bits) == pytest.approx(
            surrogate_energy(p, edges, q, imbalance_weight=IMB)
        )


def test_qubo_optimum_equals_exact_enumeration() -> None:
    p, edges, bounds = _matched_instance()
    qubo = build_qubo(p, edges, bounds, imbalance_weight=IMB)
    bits, q_energy = brute_force_qubo(qubo)
    _, e_energy = enumerate_surrogate_optimum(p, edges, bounds, imbalance_weight=IMB)
    assert q_energy == pytest.approx(e_energy)  # required: QUBO optimum == enumeration optimum


def test_qubo_optimum_coincides_with_classical_operational_plan() -> None:
    # On this crafted instance the quadratic surrogate and the L1 operational objective agree.
    p, edges, bounds = _matched_instance()
    qubo = build_qubo(p, edges, bounds, imbalance_weight=IMB)
    qplan = qubo_plan(qubo, p)
    mplan, _ = milp_plan(p)
    assert qplan.total_moved == mplan.total_moved == 6


def test_qaoa_degrades_without_qiskit() -> None:
    p, edges, bounds = _matched_instance()
    qubo = build_qubo(p, edges, bounds, imbalance_weight=IMB)
    result = solve_qaoa(qubo)
    assert isinstance(result, QaoaResult)
    if not qiskit_available():
        assert not result.available
        assert "qiskit" in result.reason  # documented reason for the skip


@pytest.mark.skipif(
    not qiskit_available(), reason="qiskit not installed (Quantum Research Mode optional)"
)
def test_qaoa_reaches_ground_state_when_available() -> None:  # pragma: no cover - needs qiskit
    p, edges, bounds = _matched_instance()
    qubo = build_qubo(p, edges, bounds, imbalance_weight=IMB)
    result = solve_qaoa(qubo)
    assert result.available
    assert result.matches_bruteforce
