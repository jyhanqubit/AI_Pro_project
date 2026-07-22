"""The rebalancing MDP — a thin control layer over the tested V2-04 simulator.

The environment reuses the exact physics of ``optimization.mpc.simulate`` (decide + feasible move
via the tested per-period solver, then realized net flow with shortage/overflow, inventory rolls
forward) so an agent's rollout is directly comparable to the mandatory policies. The only thing the
agent controls is how the per-zone *target* is shaped from the forecast:

    target = clip(capacity/2 − alpha * cum_forecast_net_over_H, 0, capacity)

That single rule subsumes the built-in policies: ``alpha=0`` is No-Action's target (stay put),
``alpha=1, H=1`` is the single-period MILP target, ``alpha=1, H=6`` is the MPC target. So the MPC
policy is *one of the actions the agent can pick* — the agent's best case is to rediscover it.

State (tabular): (hour_of_day 0..23, system_imbalance_bucket in {-1,0,+1}) → 72 states.
Action: index into ALPHAS × HORIZONS (a target-shaping control), decoded by ``decode_action``.
Reward: negative per-hour ledger cost (shortage + overflow + relocation), so maximizing return
minimizes the same ledger total the MPC benchmark ranks on.
"""

from __future__ import annotations

import numpy as np

from config.rebalancing import RebalancingCosts
from contracts.v2.ledger import LedgerAssumptions
from optimization.classical.feasibility import check_feasibility
from optimization.mpc import ZoneSpec, _solve_period, demand_series

# Discrete control grid. alpha=1 + H=6 reproduces MPC; alpha=0 reproduces No-Action.
ALPHAS: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0)
HORIZONS: tuple[int, ...] = (1, 3, 6)
N_ACTIONS = len(ALPHAS) * len(HORIZONS)
N_HOURS_OF_DAY = 24
N_IMBALANCE_BUCKETS = 3
N_STATES = N_HOURS_OF_DAY * N_IMBALANCE_BUCKETS


def decode_action(a: int) -> tuple[float, int]:
    """Action index → (alpha, horizon)."""
    return ALPHAS[a // len(HORIZONS)], HORIZONS[a % len(HORIZONS)]


def encode_state(hour_of_day: int, bikes: np.ndarray, capacity: np.ndarray) -> int:
    """(hour-of-day, coarse system imbalance) → flat state index.

    Imbalance = total bikes vs total neutral stock (sum capacity/2): bucket -1 (net short),
    0 (balanced), +1 (net long). Coarse on purpose — keeps the table small and the policy readable.
    """
    total = float(bikes.sum())
    neutral = float(capacity.sum()) / 2.0
    frac = (total - neutral) / max(neutral, 1.0)
    bucket = 1 if frac > 0.10 else (-1 if frac < -0.10 else 0)
    return (hour_of_day % 24) * N_IMBALANCE_BUCKETS + (bucket + 1)


def _target_alpha(fc_window: np.ndarray, capacity: np.ndarray, alpha: float) -> list[int]:
    """Parameterized target rule (alpha=1 == mpc._target_from_forecast)."""
    cum = fc_window.sum(axis=0)
    target = np.clip(np.rint(capacity / 2.0 - alpha * cum), 0, capacity)
    return [int(x) for x in target]


def move_toward_target(
    bikes: np.ndarray,
    capacity: np.ndarray,
    target: list[int],
    zones: list[ZoneSpec],
    costs: RebalancingCosts,
    vehicle_capacity: int,
) -> tuple[float, bool]:
    """Reposition toward ``target`` with the tested feasible solver; mutate ``bikes`` in place.

    Returns ``(moved_units, infeasible)``. On infeasibility no move is applied (empty plan), exactly
    as the mandatory-policy simulator does. Shared by the tabular and continuous (PPO) envs so both
    are provably the same physics as ``optimization.mpc.simulate``.
    """
    problem, plan = _solve_period(bikes, capacity, target, zones, costs, vehicle_capacity, "milp")
    if not check_feasibility(problem, plan).feasible:
        return 0.0, True
    moved = 0.0
    for m in plan.moves:
        i, j = problem.index_of(m.origin_id), problem.index_of(m.destination_id)
        bikes[i] -= m.quantity
        bikes[j] += m.quantity
        moved += m.quantity
    return moved, False


def apply_realized(
    bikes: np.ndarray, capacity: np.ndarray, realized_row: np.ndarray
) -> tuple[float, float]:
    """Apply one hour of realized net flow; mutate ``bikes``. Returns ``(shortage, overflow)``.

    Same order/semantics as ``optimization.mpc.simulate``: negative net is outbound demand
    (unmet → shortage), positive net is inbound (no room → overflow).
    """
    short = over = 0.0
    for j in range(len(bikes)):
        net = realized_row[j]
        if net < 0:
            demand_out = -net
            served = min(bikes[j], demand_out)
            short += demand_out - served
            bikes[j] -= served
        else:
            room = capacity[j] - bikes[j]
            accepted = min(room, net)
            over += net - accepted
            bikes[j] += accepted
    return short, over


class RebalanceEnv:
    """Seeded, offline rebalancing MDP over the V2-04 simulator.

    One episode = one full demand series (``hours`` steps). ``reset()`` re-draws the demand for the
    episode's seed; ``step(action)`` advances one hour with the chosen target-shaping control and
    returns ``(next_state, reward, done)``. Physics identical to ``optimization.mpc.simulate``.
    """

    def __init__(
        self,
        zones: list[ZoneSpec],
        A: LedgerAssumptions,
        *,
        hours: int = 72,
        vehicle_capacity: int = 18,
    ) -> None:
        self.zones = zones
        self.A = A
        self.hours = hours
        self.vehicle_capacity = vehicle_capacity
        self.capacity = np.array([z.capacity for z in zones], dtype=float)
        self.costs = RebalancingCosts(
            shortage_cost=A.shortage_externality,
            overflow_cost=A.overflow_penalty,
            distance_cost=A.reposition_cost_per_unit,
        )
        self._fc: np.ndarray | None = None
        self._realized: np.ndarray | None = None
        self.t = 0
        self.bikes = self.capacity / 2.0
        self.infeasible_periods = 0
        # Episode ledger accumulators (read after a rollout for a per-component breakdown).
        self.tot_short = 0.0
        self.tot_over = 0.0
        self.tot_moved = 0.0

    def reset(self, seed: int) -> int:
        """Start a fresh episode on ``seed`` demand; return the initial state index."""
        self._fc, self._realized = demand_series(self.zones, self.hours, seed=seed)
        self.t = 0
        self.bikes = self.capacity / 2.0
        self.infeasible_periods = 0
        self.tot_short = self.tot_over = self.tot_moved = 0.0
        return encode_state(0, self.bikes, self.capacity)

    def step(self, action: int) -> tuple[int, float, bool]:
        """Apply one control action for the current hour. Returns (next_state, reward, done)."""
        assert self._fc is not None and self._realized is not None, "call reset() first"
        alpha, horizon = decode_action(action)
        moved = 0.0

        # 1) decide + rebalance toward the alpha-shaped target (reuses the tested feasible solver).
        if alpha > 0.0:
            window = self._fc[self.t : self.t + horizon]
            target = _target_alpha(window, self.capacity, alpha)
            moved, infeasible = move_toward_target(
                self.bikes, self.capacity, target, self.zones, self.costs, self.vehicle_capacity
            )
            if infeasible:
                self.infeasible_periods += 1

        # 2) realized demand hits (same order/semantics as mpc.simulate).
        short, over = apply_realized(self.bikes, self.capacity, self._realized[self.t])

        cost = (
            short * self.A.shortage_externality
            + over * self.A.overflow_penalty
            + moved * self.A.reposition_cost_per_unit
        )
        self.tot_short += short
        self.tot_over += over
        self.tot_moved += moved
        self.t += 1
        done = self.t >= self.hours
        next_state = encode_state(self.t, self.bikes, self.capacity) if not done else 0
        return next_state, -cost, done


# --- Continuous per-zone env (for PPO) -------------------------------------------------------
# The tabular env's coarse state/action is exactly what caps its score. This env gives a learner
# the information MPC actually uses: a per-zone continuous state (inventory + own forecast) and a
# per-zone continuous action (target fraction of capacity). Same physics via the shared helpers,
# so it stays comparable to MPC on the identical ledger.

CONT_FORECAST_H = 6  # forecast look-ahead summarized into the per-zone state


class ContinuousRebalanceEnv:
    """Per-zone continuous-control version of :class:`RebalanceEnv` (same simulator physics).

    State (per step): for each zone ``[bikes_j/cap_j, cum_forecast_H_j / cap_j]`` then two global
    clock features ``[sin(2πh/24), cos(2πh/24)]`` → dim ``2·z + 2``.
    Action: ``target_frac ∈ [0,1]^z`` → per-zone target ``round(frac_j · cap_j)``; the tested solver
    then makes a feasible move toward it. Reward: negative per-hour ledger cost (same as tabular).
    """

    def __init__(
        self,
        zones: list[ZoneSpec],
        A: LedgerAssumptions,
        *,
        hours: int = 72,
        vehicle_capacity: int = 18,
    ) -> None:
        self.zones = zones
        self.A = A
        self.hours = hours
        self.vehicle_capacity = vehicle_capacity
        self.capacity = np.array([z.capacity for z in zones], dtype=float)
        self.costs = RebalancingCosts(
            shortage_cost=A.shortage_externality,
            overflow_cost=A.overflow_penalty,
            distance_cost=A.reposition_cost_per_unit,
        )
        self.n_zones = len(zones)
        self.state_dim = 2 * self.n_zones + 2
        self.action_dim = self.n_zones
        self._fc: np.ndarray | None = None
        self._realized: np.ndarray | None = None
        self.t = 0
        self.bikes = self.capacity / 2.0
        self.infeasible_periods = 0
        self.tot_short = self.tot_over = self.tot_moved = 0.0

    def _obs(self) -> np.ndarray:
        assert self._fc is not None
        window = self._fc[self.t : self.t + CONT_FORECAST_H]
        cum = window.sum(axis=0) if len(window) else np.zeros(self.n_zones)
        hour = self.t % 24
        return np.concatenate(
            [
                self.bikes / self.capacity,
                cum / self.capacity,
                [np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)],
            ]
        ).astype(float)

    def reset(self, seed: int) -> np.ndarray:
        self._fc, self._realized = demand_series(self.zones, self.hours, seed=seed)
        self.t = 0
        self.bikes = self.capacity / 2.0
        self.infeasible_periods = 0
        self.tot_short = self.tot_over = self.tot_moved = 0.0
        return self._obs()

    def step(self, target_frac: np.ndarray) -> tuple[np.ndarray, float, bool]:
        """Apply a per-zone target fraction this hour. Returns (next_obs, reward, done)."""
        assert self._realized is not None, "call reset() first"
        frac = np.clip(np.asarray(target_frac, dtype=float), 0.0, 1.0)
        target = [int(x) for x in np.rint(frac * self.capacity)]
        moved, infeasible = move_toward_target(
            self.bikes, self.capacity, target, self.zones, self.costs, self.vehicle_capacity
        )
        if infeasible:
            self.infeasible_periods += 1
        short, over = apply_realized(self.bikes, self.capacity, self._realized[self.t])
        cost = (
            short * self.A.shortage_externality
            + over * self.A.overflow_penalty
            + moved * self.A.reposition_cost_per_unit
        )
        self.tot_short += short
        self.tot_over += over
        self.tot_moved += moved
        self.t += 1
        done = self.t >= self.hours
        next_obs = self._obs() if not done else np.zeros(self.state_dim)
        return next_obs, -cost, done
