# reports/v2/ledger/ — V2-02 Profit / Regret Ledger

**Run 2026-07-20.** Reproduce: `make v2-ledger` (needs `reports/v2/holdout/promoted_model.json`
from `make v2-holdout` first). Schema/rules in `docs/v2/V2_PROFIT_REGRET_LEDGER.md`.

Artifact: `profit_regret.json` — carries the result envelope. **Unit counts are measured**
(from real demand + the real V2-01 forecast); **dollar figures are `simulated`**
(assumption-conditioned on `config/v2/assumptions.yaml`, `sourced: false`).

## Headline (assumption set `v2-assumptions-1`, single-period stocking; relocation = 0 → V2-04)

Over **114,079** H3 zone-hour decisions across the 3 V2-01 holdout windows (JC 2024):

| Policy | Net ($, simulated) | Shortage units (measured) | Overflow units (measured) | Regret vs Oracle |
|---|---|---|---|---|
| no_action (seasonal-naive stock) | 170,965 | 117,321 | 95,552 | 321,968 |
| **promoted_model** (V2-01 forecast) | **274,236** | 78,152 | 77,724 | 218,697 |
| oracle (perfect foresight, upper bound) | 492,933 | 0 | 0 | 0 |

**Predictive lift → profit:** the promoted forecast nets **+103,271** over the seasonal-naive
status quo, and the sign is **positive across all 9 cost-assumption settings** in the sensitivity
sweep (shortage externality × {0.5,1,2} × overflow penalty × {0.5,1,2}). Regret vs Oracle
(218,697) is the remaining headroom to perfect foresight.

## Integrity (enforced in code + tests)

- Contribution margin is earned only on **realized** rentals; the shortage term is the
  **externality** on unmet demand, never the lost margin (no double-count).
- Oracle (stock = actual) is an **upper bound**; regret ≥ 0 by construction (asserted at runtime).
- Costs/elasticity come from the **versioned** assumption set, each labeled `assumption`.
- Dollar figures stay `simulated` until the assumptions are sourced (`sourced: true`).
