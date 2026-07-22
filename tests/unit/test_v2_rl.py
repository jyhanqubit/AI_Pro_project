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


def test_continuous_env_shares_mpc_physics():
    """The PPO env must be the same simulator: a constant per-zone target frac == the same move,
    shortage, and overflow as feeding that target to the shared move/realized helpers."""
    from optimization.rl.env import (
        ContinuousRebalanceEnv,
        apply_realized,
        move_toward_target,
    )

    A = load_assumptions()
    zones = default_network(6)
    fc, realized = demand_series(zones, 24, seed=42)

    env = ContinuousRebalanceEnv(zones, A, hours=24)
    env.reset(42)
    # Reference rollout via the shared physics helpers with the same 0.5-fraction target.
    bikes = env.capacity / 2.0
    ref_short = ref_over = ref_moved = 0.0
    for t in range(24):
        target = [int(x) for x in np.rint(0.5 * env.capacity)]
        moved, _ = move_toward_target(bikes, env.capacity, target, zones, env.costs, 18)
        s, o = apply_realized(bikes, env.capacity, realized[t])
        ref_short += s
        ref_over += o
        ref_moved += moved
    # Env rollout with the identical constant action.
    frac = np.full(env.action_dim, 0.5)
    done = False
    while not done:
        _, _, done = env.step(frac)
    assert env.tot_short == pytest.approx(ref_short, abs=1e-6)
    assert env.tot_over == pytest.approx(ref_over, abs=1e-6)
    assert env.tot_moved == pytest.approx(ref_moved, abs=1e-6)


def test_ppo_learns_and_is_reproducible():
    """PPO must (a) reproduce bit-for-bit for a fixed seed and (b) beat a random policy — proving
    the from-scratch numpy implementation actually optimizes."""
    from optimization.rl.env import ContinuousRebalanceEnv
    from optimization.rl.ppo import PPOConfig
    from optimization.rl.ppo import greedy_return as ppo_greedy
    from optimization.rl.ppo import train as ppo_train

    A = load_assumptions()
    zones = default_network(6)
    cfg = PPOConfig(iterations=12, episodes_per_iter=4, minibatches=2, epochs=4)
    seeds = [100, 101, 102, 103]

    env = ContinuousRebalanceEnv(zones, A, hours=24)
    a1 = ppo_train(env, cfg, train_seeds=seeds)
    r1 = ppo_greedy(env, a1, eval_seed=42)
    a2 = ppo_train(ContinuousRebalanceEnv(zones, A, hours=24), cfg, train_seeds=seeds)
    r2 = ppo_greedy(ContinuousRebalanceEnv(zones, A, hours=24), a2, eval_seed=42)
    assert r1 == pytest.approx(r2)  # reproducible

    rng = np.random.default_rng(0)
    env.reset(42)
    rand_total, done = 0.0, False
    while not done:
        _, r, done = env.step(rng.random(env.action_dim))
        rand_total += r
    assert r1 > rand_total  # learned policy beats random


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
