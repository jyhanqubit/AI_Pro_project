"""V2-02 — Profit / Regret Ledger accounting (pure functions).

Turns a stocking decision + the realized demand into money, under a versioned assumption set.
The model is a single-period newsvendor per H3 zone-hour: a policy pre-positions ``stock`` bikes
to serve ``actual`` departures; unmet demand is a shortage, excess stock an overflow, and moving
away from the status-quo baseline costs relocation.

Integrity rules (CLAUDE_V2_APPEND_REVISED.md → Profit Integrity; enforced by tests):

- **Margin and externality are separate ledgers.** ``contribution_margin`` is earned only on
  realized rentals (``min(stock, actual)``). The shortage term charges the *externality* on
  unmet demand — it is NOT the lost rental revenue, so lost margin is never double-counted.
- **Oracle is an offline upper bound.** With perfect foresight the optimal single-period stock
  is ``actual`` when ``margin + shortage_externality > reposition_cost`` (documented condition),
  so Oracle stocks exactly the realized demand. Regret = Oracle net − policy net ≥ 0.

All functions are pure and vectorized over numpy arrays; no I/O, no globals.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from contracts.v2.ledger import LedgerAssumptions


@dataclass(frozen=True)
class LedgerComponents:
    """Aggregated money + unit components for one policy over an evaluation set."""

    realized_rentals: float
    shortage_units: float
    overflow_units: float
    moved_units: float
    contribution_margin: float
    shortage_cost: float
    overflow_cost: float
    relocation_cost: float
    net: float

    def as_dict(self) -> dict[str, float]:
        return {
            "realized_rentals": self.realized_rentals,
            "shortage_units": self.shortage_units,
            "overflow_units": self.overflow_units,
            "moved_units": self.moved_units,
            "contribution_margin": self.contribution_margin,
            "shortage_cost": self.shortage_cost,
            "overflow_cost": self.overflow_cost,
            "relocation_cost": self.relocation_cost,
            "net": self.net,
        }


def _nonneg_int_stock(x: np.ndarray) -> np.ndarray:
    """Stocking decisions are non-negative integers (you cannot pre-position a fraction of a bike)."""
    return np.clip(np.rint(np.asarray(x, dtype=float)), 0.0, None)


def account(
    stock: np.ndarray | list[float],
    actual: np.ndarray | list[float],
    baseline_stock: np.ndarray | list[float],
    assumptions: LedgerAssumptions,
) -> LedgerComponents:
    """Account one policy: ``stock`` served against ``actual``, relocating from ``baseline_stock``.

    ``baseline_stock`` is the status-quo position (the No-Action stock); relocation is charged on
    the units moved away from it. For the No-Action policy ``stock == baseline_stock`` → zero
    relocation.
    """
    s = _nonneg_int_stock(stock)
    d = np.asarray(actual, dtype=float)
    b = _nonneg_int_stock(baseline_stock)
    if not (s.shape == d.shape == b.shape):
        raise ValueError("stock, actual, baseline_stock must have the same shape")

    realized = np.minimum(s, d)
    shortage = np.maximum(d - s, 0.0)
    overflow = np.maximum(s - d, 0.0)
    moved = np.abs(s - b)

    contribution_margin = float(np.sum(realized) * assumptions.margin_per_rental)
    shortage_cost = float(np.sum(shortage) * assumptions.shortage_externality)
    overflow_cost = float(np.sum(overflow) * assumptions.overflow_penalty)
    relocation_cost = float(np.sum(moved) * assumptions.reposition_cost_per_unit)
    net = contribution_margin - shortage_cost - overflow_cost - relocation_cost

    return LedgerComponents(
        realized_rentals=float(np.sum(realized)),
        shortage_units=float(np.sum(shortage)),
        overflow_units=float(np.sum(overflow)),
        moved_units=float(np.sum(moved)),
        contribution_margin=contribution_margin,
        shortage_cost=shortage_cost,
        overflow_cost=overflow_cost,
        relocation_cost=relocation_cost,
        net=net,
    )


def oracle_stock(actual: np.ndarray | list[float], assumptions: LedgerAssumptions) -> np.ndarray:
    """Perfect-foresight optimal single-period stock.

    Optimal stock is exactly the realized demand when
    ``margin_per_rental + shortage_externality > reposition_cost_per_unit`` (the documented
    condition, checked here). If the condition fails the caller must not treat Oracle as an upper
    bound — we raise rather than silently return a misleading ceiling.
    """
    if not assumptions.oracle_is_upper_bound:
        raise ValueError(
            "assumption set violates margin+shortage_externality > reposition_cost; "
            "Oracle stock=actual is not the single-period optimum for this set"
        )
    return _nonneg_int_stock(actual)


def regret(policy: LedgerComponents, oracle: LedgerComponents) -> float:
    """Oracle net − policy net. ≥ 0 when Oracle is the upper bound (asserted by the runner)."""
    return oracle.net - policy.net
