# V2 Profit / Regret Ledger (V2-02)

Translates forecast quality into money without inflating the story. Predictive lift is only
useful if it survives conversion to operational profit.

## Accounting model

Per zone-hour decision, the ledger accounts:

```text
contribution_margin   = realized_rentals * margin_per_rental        (revenue side)
shortage_cost         = unmet_demand     * shortage_externality     (cost side)
overflow_cost         = dock_overflow    * overflow_penalty
relocation_cost       = moved_units      * distance_cost
------------------------------------------------------------------
net = contribution_margin - shortage_cost - overflow_cost - relocation_cost
regret = net(Oracle) - net(policy)
```

## Integrity rules (non-negotiable)

1. **Separate** contribution margin from shortage externality — they are different ledgers, not
   one number.
2. **Do not double-count**: lost margin from a stockout is captured by `shortage_cost`
   (externality) OR by reduced `contribution_margin`, never both.
3. Costs and elasticity come from a **versioned assumption set** in `config/v2/` (e.g.
   `config/v2/assumptions.yaml`), each figure labeled `claim_status: assumption`.
4. **Oracle** = perfect-foresight offline upper bound. It is a ceiling for regret, never a
   claimed achievable result.
5. Every ledger figure carries the result envelope (`run_id`/`artifact_id`/`mode`/`claim_status`/
   `freshness`).

## Assumption set (versioned)

```yaml
# config/v2/assumptions.yaml  (template — fill with sourced values, label each)
version: v2-assumptions-0
margin_per_rental: null          # assumption; cite source
shortage_externality: null       # assumption
overflow_penalty: null           # assumption
distance_cost_per_unit_km: null  # assumption
elasticity: null                 # assumption (used by V2-05 pricing)
```

## Artifact schema — `reports/v2/ledger/profit_regret.json`

```jsonc
{
  "run_id": "run_...",
  "assumption_set_version": "v2-assumptions-0",
  "by_policy": {
    "no_action": { "net": null, "regret_vs_oracle": null },
    "greedy":    { "net": null, "regret_vs_oracle": null },
    "milp":      { "net": null, "regret_vs_oracle": null },
    "mpc":       { "net": null, "regret_vs_oracle": null },
    "oracle":    { "net": null, "regret_vs_oracle": 0 }
  },
  "components": { "contribution_margin": null, "shortage_cost": null,
                  "overflow_cost": null, "relocation_cost": null },
  "claim_status": "pending"
}
```

## Acceptance

- Margin and externality separated; no double-count (add a unit test asserting the two ledgers
  never share the same event).
- Assumptions loaded from the versioned set, not inline constants.
- Oracle present and labeled as upper bound.
- Regret computed against Oracle for every policy in `V2_MPC_DECISIONING.md`.
