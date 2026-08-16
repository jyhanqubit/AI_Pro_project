"""V2-02 profit/regret ledger tests.

Lock the profit-integrity invariants (CLAUDE_V2_APPEND_REVISED.md → Profit Integrity):
- margin counts only realized rentals; the shortage term is the externality, NOT lost margin
  (no double-count);
- Oracle (stock = actual) is an upper bound, so regret ≥ 0;
- the real assumption set loads and validates.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from contracts.v2.ledger import LedgerAssumptions
from optimization.ledger import account, oracle_stock, regret

A = LedgerAssumptions(
    version="test",
    sourced=False,
    margin_per_rental=1.5,
    shortage_externality=1.0,
    overflow_penalty=0.3,
    reposition_cost_per_unit=0.4,
    distance_cost_per_unit_km=0.5,
    elasticity=-0.3,
)


def test_perfect_stock_has_no_shortage_or_overflow():
    d = np.array([3.0, 0.0, 5.0, 2.0])
    comp = account(d, d, baseline_stock=d, assumptions=A)
    assert comp.shortage_units == 0.0
    assert comp.overflow_units == 0.0
    assert comp.realized_rentals == float(d.sum())
    # net = margin * realized, no costs.
    assert comp.net == pytest.approx(1.5 * d.sum())


def test_margin_counts_only_realized_not_lost_no_double_count():
    # Under-stock: demand 10, stock 4 -> realized 4, shortage 6.
    comp = account([4.0], [10.0], baseline_stock=[4.0], assumptions=A)
    assert comp.realized_rentals == 4.0
    assert comp.shortage_units == 6.0
    # Margin is on the 4 realized only (lost 6 are NOT earned).
    assert comp.contribution_margin == pytest.approx(1.5 * 4)
    # Shortage cost is the externality on 6 unmet, NOT 6*margin (no double-count of lost margin).
    assert comp.shortage_cost == pytest.approx(1.0 * 6)
    # net = 4*1.5 - 6*1.0 - 0 - 0
    assert comp.net == pytest.approx(6.0 - 6.0)


def test_overflow_charged_on_excess():
    comp = account([10.0], [4.0], baseline_stock=[10.0], assumptions=A)
    assert comp.overflow_units == 6.0
    assert comp.realized_rentals == 4.0
    assert comp.overflow_cost == pytest.approx(0.3 * 6)
    assert comp.net == pytest.approx(1.5 * 4 - 0.3 * 6)


def test_oracle_is_upper_bound_regret_nonnegative():
    rng = np.random.default_rng(0)
    actual = rng.integers(0, 12, size=500).astype(float)
    forecast = np.clip(actual + rng.normal(0, 3, size=500), 0, None)
    seasonal = np.clip(actual + rng.normal(0, 5, size=500), 0, None)
    o = account(oracle_stock(actual, A), actual, baseline_stock=oracle_stock(actual, A), assumptions=A)
    for stock in (forecast, seasonal):
        pol = account(np.rint(stock), actual, baseline_stock=np.rint(stock), assumptions=A)
        assert regret(pol, o) >= -1e-9  # oracle nets at least as much as any policy


def test_better_forecast_earns_more_net():
    rng = np.random.default_rng(1)
    actual = rng.integers(0, 12, size=1000).astype(float)
    good = np.clip(actual + rng.normal(0, 1, size=1000), 0, None)  # tight
    bad = np.clip(actual + rng.normal(0, 6, size=1000), 0, None)  # loose
    good_net = account(np.rint(good), actual, baseline_stock=np.rint(good), assumptions=A).net
    bad_net = account(np.rint(bad), actual, baseline_stock=np.rint(bad), assumptions=A).net
    assert good_net > bad_net  # accuracy translates to money


def test_oracle_requires_upper_bound_condition():
    bad = A.model_copy(update={"reposition_cost_per_unit": 99.0})
    assert bad.oracle_is_upper_bound is False
    with pytest.raises(ValueError):
        oracle_stock([1.0, 2.0], bad)


def test_shape_mismatch_rejected():
    with pytest.raises(ValueError):
        account([1.0, 2.0], [1.0], baseline_stock=[1.0, 2.0], assumptions=A)


def test_real_assumption_set_loads_and_validates():
    path = Path("config/v2/assumptions.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    a = LedgerAssumptions.model_validate(data)
    assert a.version == "v2-assumptions-1"
    assert a.sourced is False  # honesty: not yet sourced
    assert a.oracle_is_upper_bound is True
