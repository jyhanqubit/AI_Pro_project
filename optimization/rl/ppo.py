"""From-scratch PPO in pure numpy (no torch — keeps the RL module dependency-light).

A compact but faithful PPO: a one-hidden-layer MLP policy (diagonal Gaussian with a
state-independent log-std, actions clipped to [0,1] in the env), a separate MLP critic, GAE(λ)
advantages, the clipped surrogate objective, an entropy bonus, and an Adam step — all with manual
backprop. It trains the per-zone :class:`ContinuousRebalanceEnv`, which hands the policy the
per-zone forecast MPC uses, so PPO can express a per-zone target the tabular agent structurally
could not.

Fully seeded and offline (no online/streaming updates on live users — that is prohibited).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from optimization.rl.env import ContinuousRebalanceEnv

LOG_2PI = float(np.log(2.0 * np.pi))


@dataclass(frozen=True)
class PPOConfig:
    iterations: int = 60
    episodes_per_iter: int = 6
    hidden: int = 64
    lr: float = 3e-3
    gamma: float = 0.97
    lam: float = 0.95
    clip: float = 0.2
    epochs: int = 6
    minibatches: int = 4
    ent_coef: float = 0.003
    vf_coef: float = 0.5
    init_log_std: float = -0.5
    seed: int = 11


class _MLP:
    """One hidden layer, tanh. Manual forward/backward; Adam state lives on the params."""

    def __init__(self, n_in: int, n_hidden: int, n_out: int, rng: np.random.Generator) -> None:
        # He-ish init for tanh; small final layer so the initial policy is near-neutral.
        self.W1 = rng.normal(0, np.sqrt(2.0 / n_in), (n_in, n_hidden))
        self.b1 = np.zeros(n_hidden)
        self.W2 = rng.normal(0, 0.01, (n_hidden, n_out))
        self.b2 = np.zeros(n_out)
        self._cache: tuple[np.ndarray, np.ndarray] | None = None
        # Adam moments, keyed by param name.
        self._m = {k: np.zeros_like(getattr(self, k)) for k in ("W1", "b1", "W2", "b2")}
        self._v = {k: np.zeros_like(getattr(self, k)) for k in ("W1", "b1", "W2", "b2")}

    def forward(self, x: np.ndarray) -> np.ndarray:
        h = np.tanh(x @ self.W1 + self.b1)
        self._cache = (x, h)
        return h @ self.W2 + self.b2

    def backward(self, d_out: np.ndarray) -> dict[str, np.ndarray]:
        x, h = self._cache  # type: ignore[misc]
        d_w2 = h.T @ d_out
        d_b2 = d_out.sum(axis=0)
        d_h = d_out @ self.W2.T
        d_z = d_h * (1.0 - h * h)
        d_w1 = x.T @ d_z
        d_b1 = d_z.sum(axis=0)
        return {"W1": d_w1, "b1": d_b1, "W2": d_w2, "b2": d_b2}

    def adam_step(
        self,
        grads: dict[str, np.ndarray],
        lr: float,
        step: int,
        b1: float = 0.9,
        b2: float = 0.999,
        eps: float = 1e-8,
    ) -> None:
        for k, g in grads.items():
            self._m[k] = b1 * self._m[k] + (1 - b1) * g
            self._v[k] = b2 * self._v[k] + (1 - b2) * (g * g)
            m_hat = self._m[k] / (1 - b1**step)
            v_hat = self._v[k] / (1 - b2**step)
            setattr(self, k, getattr(self, k) - lr * m_hat / (np.sqrt(v_hat) + eps))


@dataclass
class _Rollout:
    obs: list[np.ndarray] = field(default_factory=list)
    act: list[np.ndarray] = field(default_factory=list)
    logp: list[float] = field(default_factory=list)
    val: list[float] = field(default_factory=list)
    rew: list[float] = field(default_factory=list)
    done: list[bool] = field(default_factory=list)


class PPO:
    """PPO agent for :class:`ContinuousRebalanceEnv`. Deterministic for a fixed config + seeds."""

    def __init__(self, state_dim: int, action_dim: int, cfg: PPOConfig) -> None:
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.pi = _MLP(state_dim, cfg.hidden, action_dim, self.rng)
        self.vf = _MLP(state_dim, cfg.hidden, 1, self.rng)
        self.log_std = np.full(action_dim, cfg.init_log_std)
        self._ls_m = np.zeros(action_dim)
        self._ls_v = np.zeros(action_dim)
        self._adam_step = 0

    # --- policy distribution helpers -----------------------------------------------------------
    def _logp(self, mean: np.ndarray, act: np.ndarray) -> np.ndarray:
        std = np.exp(self.log_std)
        z = (act - mean) / std
        return -0.5 * (z * z + 2 * self.log_std + LOG_2PI).sum(axis=-1)

    def act(self, obs: np.ndarray, *, greedy: bool = False) -> tuple[np.ndarray, float, float]:
        """Return (action, logp, value). Greedy uses the mean (for evaluation)."""
        mean = self.pi.forward(obs[None, :])[0]
        val = float(self.vf.forward(obs[None, :])[0, 0])
        if greedy:
            return mean, 0.0, val
        std = np.exp(self.log_std)
        act = mean + std * self.rng.standard_normal(mean.shape)
        return act, float(self._logp(mean[None, :], act[None, :])[0]), val

    # --- GAE -----------------------------------------------------------------------------------
    def _gae(self, roll: _Rollout) -> tuple[np.ndarray, np.ndarray]:
        rew, val, done = np.array(roll.rew), np.array(roll.val), np.array(roll.done)
        adv = np.zeros_like(rew)
        last = 0.0
        for t in reversed(range(len(rew))):
            next_v = 0.0 if done[t] else (val[t + 1] if t + 1 < len(val) else 0.0)
            delta = rew[t] + self.cfg.gamma * next_v - val[t]
            last = delta + self.cfg.gamma * self.cfg.lam * (0.0 if done[t] else last)
            adv[t] = last
        return adv, adv + val

    # --- training ------------------------------------------------------------------------------
    def update(self, obs, act, logp_old, adv, ret) -> None:
        cfg = self.cfg
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        n = len(obs)
        idx = np.arange(n)
        for _ in range(cfg.epochs):
            self.rng.shuffle(idx)
            for mb in np.array_split(idx, cfg.minibatches):
                self._adam_step += 1
                o, a, lpo, ad, rt = obs[mb], act[mb], logp_old[mb], adv[mb], ret[mb]
                mean = self.pi.forward(o)
                logp = self._logp(mean, a)
                ratio = np.exp(logp - lpo)
                clipped = np.clip(ratio, 1 - cfg.clip, 1 + cfg.clip)
                use_unclipped = (ratio * ad) <= (clipped * ad)
                # d(-surrogate)/dlogp: ratio*adv where the unclipped branch is active, else 0.
                d_logp = -(np.where(use_unclipped, ratio * ad, 0.0)) / len(mb)
                std = np.exp(self.log_std)
                d_mean = d_logp[:, None] * (a - mean) / (std * std)
                d_ls_pg = (d_logp[:, None] * (((a - mean) ** 2) / (std * std) - 1.0)).sum(axis=0)
                d_ls_ent = -cfg.ent_coef * np.ones_like(
                    self.log_std
                )  # entropy grad wrt log_std = 1
                self.pi.adam_step(self.pi.backward(d_mean), cfg.lr, self._adam_step)
                # value regression
                v = self.vf.forward(o)[:, 0]
                d_v = (cfg.vf_coef * 2.0 * (v - rt) / len(mb))[:, None]
                self.vf.adam_step(self.vf.backward(d_v), cfg.lr, self._adam_step)
                # log-std Adam (policy-gradient term + entropy bonus)
                g_ls = d_ls_pg + d_ls_ent
                self._ls_m = 0.9 * self._ls_m + 0.1 * g_ls
                self._ls_v = 0.999 * self._ls_v + 0.001 * (g_ls * g_ls)
                m_hat = self._ls_m / (1 - 0.9**self._adam_step)
                v_hat = self._ls_v / (1 - 0.999**self._adam_step)
                self.log_std = np.clip(
                    self.log_std - cfg.lr * m_hat / (np.sqrt(v_hat) + 1e-8), -3.0, 1.0
                )


def train(env: ContinuousRebalanceEnv, cfg: PPOConfig, *, train_seeds: list[int]) -> PPO:
    """Train PPO on episodes drawn from ``train_seeds``. Deterministic for fixed inputs."""
    agent = PPO(env.state_dim, env.action_dim, cfg)
    ep = 0
    for _ in range(cfg.iterations):
        roll = _Rollout()
        for _ in range(cfg.episodes_per_iter):
            seed = int(train_seeds[ep % len(train_seeds)])
            ep += 1
            obs = env.reset(seed)
            done = False
            while not done:
                a, lp, v = agent.act(obs)
                nobs, r, done = env.step(a)
                roll.obs.append(obs)
                roll.act.append(a)
                roll.logp.append(lp)
                roll.val.append(v)
                roll.rew.append(r)
                roll.done.append(done)
                obs = nobs
        adv, ret = agent._gae(roll)
        agent.update(np.array(roll.obs), np.array(roll.act), np.array(roll.logp), adv, ret)
    return agent


def greedy_return(env: ContinuousRebalanceEnv, agent: PPO, *, eval_seed: int) -> float:
    """Roll out the mean (greedy) policy on the eval scenario; return total reward."""
    obs = env.reset(eval_seed)
    total, done = 0.0, False
    while not done:
        a, _, _ = agent.act(obs, greedy=True)
        obs, r, done = env.step(a)
        total += r
    return total
