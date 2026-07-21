"""V2-04 multi-period MPC policy-comparison tests.

Lock the invariants: every policy stays feasible, Oracle is an upper bound (regret >= 0), the
multi-period MPC beats myopic no-action, the run is deterministic, and unit tallies are
non-negative. Small scenario so the suite stays fast.
"""

from __future__ import annotations

import numpy as np

from contracts.v2.ledger import LedgerAssumptions
from optimization.mpc import PolicyResult, default_network, demand_series, simulate

A = LedgerAssumptions(
    version="test", sourced=False, margin_per_rental=1.5, shortage_externality=1.0,
    overflow_penalty=0.3, reposition_cost_per_unit=0.4, distance_cost_per_unit_km=0.5, elasticity=-0.3,
)
POLICIES = ("no_action", "greedy", "milp", "mpc", "oracle")


def _run_all(hours=48, zones=6, seed=1):
    zs = default_network(zones)
    fc, realized = demand_series(zs, hours, seed=seed)
    return {p: simulate(p, zs, fc, realized, A, horizon=6) for p in POLICIES}


def test_all_policies_feasible_and_nonnegative():
    res = _run_all()
    for p, r in res.items():
        assert isinstance(r, PolicyResult)
        assert r.feasible, f"{p} produced an infeasible period"
        assert r.shortage_units >= 0 and r.overflow_units >= 0 and r.moved_units >= 0
        assert r.total_cost >= 0


def test_oracle_is_upper_bound_regret_nonnegative():
    res = _run_all()
    oracle_net = res["oracle"].net
    for p, r in res.items():
        assert oracle_net - r.net >= -1e-6, f"{p} beats Oracle — not an upper bound"


def test_mpc_beats_no_action():
    res = _run_all()
    # Multi-period MPC should cost less than doing nothing on this commute scenario.
    assert res["mpc"].total_cost < res["no_action"].total_cost


def test_mpc_at_least_as_good_as_single_period_milp():
    res = _run_all()
    # Longer look-ahead should not be worse than the 1-hour MILP (allow tiny slack).
    assert res["mpc"].total_cost <= res["milp"].total_cost + 1e-6


def test_deterministic():
    a = _run_all(seed=7)
    b = _run_all(seed=7)
    for p in POLICIES:
        assert a[p].total_cost == b[p].total_cost


def test_no_action_moves_nothing():
    res = _run_all()
    assert res["no_action"].moved_units == 0.0
    assert res["no_action"].relocation_cost == 0.0


def test_demand_series_shapes():
    zs = default_network(5)
    fc, realized = demand_series(zs, 24, seed=3)
    assert fc.shape == (24, 5) and realized.shape == (24, 5)
    # forecast is the deterministic mean; realized differs (noise added).
    assert not np.allclose(fc, realized)
