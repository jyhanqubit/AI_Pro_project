"""QUBO formulation of small rebalancing instances. **Quantum Research Mode** (CLAUDE.md §14.2).

Research-only. QUBO/QAOA outputs must never feed Demo, Historical Replay, or Live views
(CLAUDE.md §3); the operator-facing plan always comes from the classical solvers. This module
maps a *small* rebalancing instance to a Quadratic Unconstrained Binary Optimization problem so
it can be handed to QAOA (``qaoa.py``), and — critically — validates the encoding against exact
enumeration (§14.1 step 4, §14.2).

Variable mapping (documented, §14.2)
------------------------------------
* Choose a small set of directed edges ``(origin, destination)``. Each edge carries an integer
  bike flow ``x_e in [0, U_e]``.
* Each ``x_e`` is binary-encoded with bounded coefficients ``w_e = [1, 2, 4, ..., r]`` so that
  ``x_e = sum_k w_e[k] * b_{e,k}`` ranges over exactly ``[0, U_e]`` (no value exceeds ``U_e``).
* Final inventory ``f_i = bikes_i - sum_{e: origin i} x_e + sum_{e: dest i} x_e``.

Energy (the surrogate objective the QUBO minimises)
---------------------------------------------------
    E(x) = imbalance_weight * sum_i (f_i - target_i)^2  +  distance_cost * sum_e d_e * x_e

This is a **quadratic imbalance surrogate** of the operational objective in
``optimization.classical.objective`` (which uses asymmetric L1 shortage/overflow costs). The
edge bounds ``U_e`` are chosen so every point in the encoding box is operationally feasible, so
no penalty terms are needed and the QUBO optimum is directly comparable to exact enumeration of
the same surrogate. We do **not** claim the surrogate optimum equals the L1 operational optimum
in general, nor any quantum advantage (§14.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from optimization.classical.problem import Move, RebalancingPlan, RebalancingProblem


def bounded_binary_weights(upper: int) -> list[int]:
    """Bounded-coefficient weights whose subset sums cover exactly ``[0, upper]``."""
    if upper <= 0:
        return []
    weights: list[int] = []
    remaining = upper
    power = 1
    while remaining > 0:
        w = min(power, remaining)
        weights.append(w)
        remaining -= w
        power *= 2
    return weights


@dataclass(frozen=True)
class QuboProblem:
    """A QUBO: minimise ``offset + sum_v linear[v] b_v + sum_{u<v} quad[(u,v)] b_u b_v``."""

    linear: dict[int, float]
    quadratic: dict[tuple[int, int], float]
    offset: float
    num_vars: int
    # decode metadata: for each edge, (origin_idx, dest_idx, [(bit_index, weight), ...])
    edges: tuple[tuple[int, int], ...]
    bit_map: tuple[tuple[tuple[int, int], ...], ...] = field(default=())

    def energy(self, bits: tuple[int, ...]) -> float:
        e = self.offset
        for v, coeff in self.linear.items():
            if bits[v]:
                e += coeff
        for (u, v), coeff in self.quadratic.items():
            if bits[u] and bits[v]:
                e += coeff
        return e

    def decode_quantities(self, bits: tuple[int, ...]) -> list[int]:
        return [sum(w for (bi, w) in edge_bits if bits[bi]) for edge_bits in self.bit_map]


def build_qubo(
    problem: RebalancingProblem,
    edges: list[tuple[int, int]],
    upper_bounds: list[int],
    *,
    imbalance_weight: float = 10.0,
) -> QuboProblem:
    """Build the QUBO for the given directed edges and per-edge upper bounds."""
    if len(edges) != len(upper_bounds):
        raise ValueError("edges and upper_bounds must have equal length")

    # Assign binary variables per edge.
    bit_map: list[tuple[tuple[int, int], ...]] = []
    next_bit = 0
    for u in upper_bounds:
        weights = bounded_binary_weights(u)
        bit_map.append(tuple((next_bit + k, w) for k, w in enumerate(weights)))
        next_bit += len(weights)
    num_vars = next_bit

    linear: dict[int, float] = {}
    quadratic: dict[tuple[int, int], float] = {}
    offset = 0.0

    def add_linear(v: int, c: float) -> None:
        linear[v] = linear.get(v, 0.0) + c

    def add_quad(a: int, b: int, c: float) -> None:
        key = (a, b) if a < b else (b, a)
        quadratic[key] = quadratic.get(key, 0.0) + c

    n = len(problem.stations)
    dist_cost = problem.costs.distance_cost

    # Distance term: distance_cost * sum_e d_e * x_e  (linear in bits).
    for e, (i, j) in enumerate(edges):
        d = problem.distance_km(i, j)
        for bi, w in bit_map[e]:
            add_linear(bi, dist_cost * d * w)

    # Imbalance term: imbalance_weight * sum_i (a_i + L_i)^2, a_i = bikes_i - target_i,
    # L_i = sum over bits of coeff_{i,bit} * bit, coeff = sign(edge at i) * weight.
    for i in range(n):
        a_i = float(problem.stations[i].bikes - problem.stations[i].target)
        # coefficient per bit variable for station i
        coeffs: dict[int, float] = {}
        for e, (o, dst) in enumerate(edges):
            sign = 0.0
            if o == i:
                sign = -1.0
            elif dst == i:
                sign = 1.0
            if sign == 0.0:
                continue
            for bi, w in bit_map[e]:
                coeffs[bi] = coeffs.get(bi, 0.0) + sign * w

        offset += imbalance_weight * a_i * a_i
        items = list(coeffs.items())
        for bi, c in items:
            # 2*a_i*c*b + c^2*b  (b^2 = b)
            add_linear(bi, imbalance_weight * (2.0 * a_i * c + c * c))
        for x in range(len(items)):
            for y in range(x + 1, len(items)):
                bi_x, c_x = items[x]
                bi_y, c_y = items[y]
                add_quad(bi_x, bi_y, imbalance_weight * 2.0 * c_x * c_y)

    return QuboProblem(
        linear=linear,
        quadratic=quadratic,
        offset=offset,
        num_vars=num_vars,
        edges=tuple(edges),
        bit_map=tuple(bit_map),
    )


def surrogate_energy(
    problem: RebalancingProblem,
    edges: list[tuple[int, int]],
    quantities: list[int],
    *,
    imbalance_weight: float = 10.0,
) -> float:
    """The QUBO's target energy computed directly from integer move quantities."""
    final = [float(s.bikes) for s in problem.stations]
    dist_term = 0.0
    for (i, j), q in zip(edges, quantities, strict=True):
        final[i] -= q
        final[j] += q
        dist_term += problem.costs.distance_cost * problem.distance_km(i, j) * q
    imb = sum((final[i] - problem.stations[i].target) ** 2 for i in range(len(problem.stations)))
    return imbalance_weight * imb + dist_term


def brute_force_qubo(qubo: QuboProblem) -> tuple[tuple[int, ...], float]:
    """Exhaustively minimise the QUBO over all 2**num_vars binary assignments."""
    best_bits: tuple[int, ...] = tuple(0 for _ in range(qubo.num_vars))
    best_energy = qubo.energy(best_bits)
    for combo in product((0, 1), repeat=qubo.num_vars):
        e = qubo.energy(combo)
        if e < best_energy:
            best_energy = e
            best_bits = combo
    return best_bits, best_energy


def enumerate_surrogate_optimum(
    problem: RebalancingProblem,
    edges: list[tuple[int, int]],
    upper_bounds: list[int],
    *,
    imbalance_weight: float = 10.0,
) -> tuple[list[int], float]:
    """Exact minimum of the surrogate energy over integer moves in the encoding boxes."""
    best_q = [0 for _ in edges]
    best_e = surrogate_energy(problem, edges, best_q, imbalance_weight=imbalance_weight)
    for q in product(*[range(u + 1) for u in upper_bounds]):
        e = surrogate_energy(problem, edges, list(q), imbalance_weight=imbalance_weight)
        if e < best_e:
            best_e = e
            best_q = list(q)
    return best_q, best_e


def qubo_plan(qubo: QuboProblem, problem: RebalancingProblem) -> RebalancingPlan:
    """Solve the QUBO by brute force and decode it to a rebalancing plan (research only)."""
    bits, _ = brute_force_qubo(qubo)
    quantities = qubo.decode_quantities(bits)
    moves = tuple(
        Move(
            origin_id=problem.stations[i].station_id,
            destination_id=problem.stations[j].station_id,
            quantity=q,
            distance_km=round(problem.distance_km(i, j), 4),
        )
        for (i, j), q in zip(qubo.edges, quantities, strict=True)
        if q > 0
    )
    return RebalancingPlan(moves=moves, solver="qubo")
