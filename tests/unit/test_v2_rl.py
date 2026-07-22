"""Research-Mode RL rebalancing — fidelity to the V2-04 simulator + reproducibility + honesty.

The key acceptance is *fidelity*: the RL environment must be the SAME MDP as the mandatory-policy
simulator, so a learned policy is comparable to MPC on the same ledger. We prove it by driving the
env with the fixed control that equals MPC (alpha=1, H=6) and No-Action (alpha=0) and matching
``optimization.mpc.simulate`` unit-for-unit.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from contracts.v2.envelope import ResultEnvelope
from optimization.ledger_run import load_assumptions
from optimization.mpc import default_network, demand_series, simulate
from optimization.rl.env import ALPHAS, HORIZONS, RebalanceEnv, decode_action
from optimization.rl.qlearning import QLearnConfig, greedy_return, train


def _action(alpha: float, horizon: int) -> int:
    return ALPHAS.index(alpha) * len(HORIZONS) + HORIZONS.index(horizon)


def _rollout_fixed(env: RebalanceEnv, action: int, seed: int) -> float:
    env.reset(seed)
    total, done = 0.0, False
    while not done:
        _, r, done = env.step(action)
        total += r
    return total


def test_env_matches_mpc_simulate_for_mpc_action():
    """alpha=1, H=6 in the env == the built-in MPC policy (same physics, same ledger)."""
    A = load_assumptions()
    zones = default_network(8)
    fc, realized = demand_series(zones, 72, seed=42)
    mpc = simulate("mpc", zones, fc, realized, A, horizon=6)

    env = RebalanceEnv(zones, A, hours=72)
    _rollout_fixed(env, _action(1.0, 6), seed=42)
    assert env.tot_short == pytest.approx(mpc.shortage_units, abs=1e-6)
    assert env.tot_over == pytest.approx(mpc.overflow_units, abs=1e-6)
    assert env.tot_moved == pytest.approx(mpc.moved_units, abs=1e-6)


def test_env_matches_no_action_for_alpha_zero():
    """alpha=0 never moves — must equal the No-Action policy."""
    A = load_assumptions()
    zones = default_network(8)
    fc, realized = demand_series(zones, 72, seed=42)
    noop = simulate("no_action", zones, fc, realized, A)

    env = RebalanceEnv(zones, A, hours=72)
    total = _rollout_fixed(env, _action(0.0, 1), seed=42)
    assert env.tot_moved == 0.0
    assert env.tot_short == pytest.approx(noop.shortage_units, abs=1e-6)
    assert env.tot_over == pytest.approx(noop.overflow_units, abs=1e-6)
    # reward is the negative ledger cost
    assert total == pytest.approx(-noop.total_cost, abs=1e-6)


def test_training_is_reproducible():
    """Same seeds + config → identical Q-table (the artifact must be reproducible)."""
    A = load_assumptions()
    zones = default_network(6)
    cfg = QLearnConfig(episodes=8)
    seeds = [100, 101, 102]
    q1 = train(RebalanceEnv(zones, A, hours=24), cfg, train_seeds=seeds)
    q2 = train(RebalanceEnv(zones, A, hours=24), cfg, train_seeds=seeds)
    assert np.array_equal(q1, q2)


def test_greedy_rollout_is_deterministic():
    A = load_assumptions()
    zones = default_network(6)
    env = RebalanceEnv(zones, A, hours=24)
    q = train(env, QLearnConfig(episodes=8), train_seeds=[100, 101])
    r1, a1 = greedy_return(env, q, eval_seed=42)
    r2, a2 = greedy_return(env, q, eval_seed=42)
    assert r1 == pytest.approx(r2)
    assert a1 == a2


def test_decode_action_roundtrip_covers_mpc_and_noaction():
    assert decode_action(_action(1.0, 6)) == (1.0, 6)  # MPC
    assert decode_action(_action(0.0, 1))[0] == 0.0  # No-Action


def test_research_value_blocked_off_research_surface():
    """The honesty contract: a research result may not surface in a product mode."""
    from datetime import UTC, datetime

    ok = ResultEnvelope[dict](
        value={"beats_mpc": False},
        run_id="run_rl_test",
        artifact_id="reports/v2/research/rl_rebalancing.json",
        mode="research",
        claim_status="research",
        freshness=datetime.now(UTC),
    )
    assert ok.claim_status.value == "research"
    with pytest.raises(ValidationError):
        ResultEnvelope[dict](
            value={"beats_mpc": False},
            run_id="run_rl_test",
            artifact_id="reports/v2/research/rl_rebalancing.json",
            mode="live",
            claim_status="research",
            freshness=datetime.now(UTC),
        )
