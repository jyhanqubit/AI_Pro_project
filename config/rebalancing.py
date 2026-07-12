"""Rebalancing / optimization configuration. CLAUDE.md section 14.

Operational cost weights and the vehicle-capacity limit live here so a plan is reproducible
from configuration and the objective is auditable (sections 14.1, 16). Costs are asymmetric:
a shortage (a rider finds no bike) is weighted more heavily than an overflow (a returning
rider finds no dock / a bike sits idle), mirroring the asymmetric operational metric used in
Phase 06 (docs/EVALUATION_PROTOCOL.md).
"""

from __future__ import annotations

from dataclasses import dataclass

# Version stamp persisted with every plan so a cost change is traceable to configuration.
REBALANCING_CONFIG_VERSION = "rebal-v1"

# Cost per unit of unmet demand at a station (final bikes below target). Highest weight: a
# stockout directly loses a trip.
DEFAULT_SHORTAGE_COST = 3.0
# Cost per unit of over-supply (final bikes above target): wasted inventory and fewer free
# docks for returns. Lower than shortage -> asymmetric objective.
DEFAULT_OVERFLOW_COST = 1.0
# Cost per bike-kilometre relocated (truck time / labour). Keeps plans from shuffling bikes
# across the whole city for a marginal imbalance gain.
DEFAULT_DISTANCE_COST = 0.5
# Soft-constraint penalty weight used only by the QUBO surrogate (Quantum Research Mode) to
# discourage constraint violations; the classical solvers treat these as hard constraints.
DEFAULT_CONSTRAINT_PENALTY = 100.0

# Maximum total bikes a single rebalancing run may move (one truck tour). A binding limit
# forces the solver to prioritise the highest-cost shortages.
DEFAULT_VEHICLE_CAPACITY = 18


@dataclass(frozen=True)
class RebalancingCosts:
    """Weights of the operational objective (section 14.1)."""

    shortage_cost: float = DEFAULT_SHORTAGE_COST
    overflow_cost: float = DEFAULT_OVERFLOW_COST
    distance_cost: float = DEFAULT_DISTANCE_COST
    constraint_penalty: float = DEFAULT_CONSTRAINT_PENALTY
    version: str = REBALANCING_CONFIG_VERSION
