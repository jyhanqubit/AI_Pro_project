"""Dependency-light tabular Q-learning (numpy only — torch is not a project dependency).

Standard ε-greedy Q-learning over the discrete ``RebalanceEnv`` state/action tables. Kept
deliberately simple and fully seeded: the same ``train_seeds`` + hyperparameters reproduce the
same Q-table bit-for-bit, so the research artifact is reproducible. No online/streaming updates —
training is a closed offline loop over simulated episodes (the prohibited "online learning /
bandits" rule is about learning on live users, which this is not).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from optimization.rl.env import N_ACTIONS, N_STATES, RebalanceEnv


@dataclass(frozen=True)
class QLearnConfig:
    episodes: int = 300
    alpha_lr: float = 0.10  # learning rate
    gamma: float = 0.95  # discount
    eps_start: float = 0.50
    eps_end: float = 0.02
    seed: int = 7  # RNG seed for ε-greedy exploration + training-demand seeds


def _epsilon(ep: int, cfg: QLearnConfig) -> float:
    """Linear ε decay from eps_start to eps_end over the run."""
    if cfg.episodes <= 1:
        return cfg.eps_end
    frac = ep / (cfg.episodes - 1)
    return cfg.eps_start + (cfg.eps_end - cfg.eps_start) * frac


def train(env: RebalanceEnv, cfg: QLearnConfig, *, train_seeds: list[int]) -> np.ndarray:
    """Train a Q-table on episodes drawn from ``train_seeds`` (never the eval seed).

    Returns the learned Q-table of shape (N_STATES, N_ACTIONS). Deterministic for fixed inputs.
    """
    rng = np.random.default_rng(cfg.seed)
    q = np.zeros((N_STATES, N_ACTIONS), dtype=float)
    for ep in range(cfg.episodes):
        eps = _epsilon(ep, cfg)
        seed = int(train_seeds[ep % len(train_seeds)])
        s = env.reset(seed)
        done = False
        while not done:
            if rng.random() < eps:
                a = int(rng.integers(N_ACTIONS))
            else:
                a = int(_argmax_tiebroken(q[s], rng))
            s2, r, done = env.step(a)
            best_next = 0.0 if done else float(q[s2].max())
            q[s, a] += cfg.alpha_lr * (r + cfg.gamma * best_next - q[s, a])
            s = s2
    return q


def _argmax_tiebroken(row: np.ndarray, rng: np.random.Generator) -> int:
    """Argmax with random tie-break (so unvisited-equal actions don't bias toward index 0)."""
    m = row.max()
    ties = np.flatnonzero(row >= m - 1e-12)
    return int(ties[0]) if ties.size == 1 else int(rng.choice(ties))


def greedy_return(env: RebalanceEnv, q: np.ndarray, *, eval_seed: int) -> tuple[float, list[int]]:
    """Roll out the greedy policy from ``q`` on the eval scenario; return (total, actions)."""
    s = env.reset(eval_seed)
    total = 0.0
    actions: list[int] = []
    done = False
    while not done:
        a = int(np.argmax(q[s]))
        actions.append(a)
        s, r, done = env.step(a)
        total += r
    return total, actions
