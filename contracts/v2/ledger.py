"""V2-02 profit/regret ledger contracts.

Typed boundary for the versioned assumption set and per-policy ledger output. The accounting
lives in ``optimization.ledger`` (pure functions); these models validate what goes in (the
assumptions) and what comes out (a policy's money components), and carry the honesty labels.
"""

from __future__ import annotations

from pydantic import Field

from contracts.common import ContractModel


class LedgerAssumptions(ContractModel):
    """The versioned cost/elasticity assumption set (``config/v2/assumptions.yaml``).

    Every field is an ``assumption`` — a modeling input, not a measured economic figure. The
    ledger's dollar outputs are only as good as these, hence ``sourced`` and the required
    sensitivity sweep.
    """

    version: str = Field(min_length=1)
    sourced: bool = Field(description="False until each value is replaced with a cited source.")
    margin_per_rental: float = Field(ge=0.0)
    shortage_externality: float = Field(ge=0.0)
    overflow_penalty: float = Field(ge=0.0)
    reposition_cost_per_unit: float = Field(ge=0.0)
    distance_cost_per_unit_km: float = Field(ge=0.0)
    elasticity: float
    notes: str = ""

    @property
    def oracle_is_upper_bound(self) -> bool:
        """Single-period condition for Oracle (stock=actual) to maximize net (see the yaml notes)."""
        return self.margin_per_rental + self.shortage_externality > self.reposition_cost_per_unit


class PolicyLedger(ContractModel):
    """Money components for one stocking policy over an evaluation set.

    Integrity: ``contribution_margin`` counts only realized rentals; ``shortage_cost`` is the
    externality on unmet demand and is NOT the lost margin (no double-count). ``net`` subtracts
    the three cost terms from margin; ``regret_vs_oracle`` = Oracle net − this policy's net.
    """

    policy: str = Field(min_length=1)
    # Measured unit counts (from real demand + real forecast).
    realized_rentals: float = Field(ge=0.0)
    shortage_units: float = Field(ge=0.0)
    overflow_units: float = Field(ge=0.0)
    moved_units: float = Field(ge=0.0)
    # Assumption-conditioned dollar terms (claim_status: simulated).
    contribution_margin: float
    shortage_cost: float = Field(ge=0.0)
    overflow_cost: float = Field(ge=0.0)
    relocation_cost: float = Field(ge=0.0)
    net: float
    regret_vs_oracle: float = Field(ge=0.0, description="Oracle net − policy net; >= 0 by construction.")
