# V2 LLM Incremental Value Ablation (V2-03)

The core V2 question: does the **LLM** event layer add value over a plain **rule** layer, after
its own cost? This requires cleanly separating three feature arms and reporting net-of-cost lift.

## Three arms (identical cutoffs/splits)

```text
A0  No-Event    : demand history + calendar only
A1  Rule-Event  : A0 + deterministic rule-based event features
                  (keyword/geo/time rules — no LLM)
A2  LLM-Event   : A0 + LLM-extracted + graph-propagated event features
```

All three run on the **same** rolling H3 holdout windows (`V2_EVALUATION_PROTOCOL.md`) with the
same seed. Arms differ only in features.

## What is measured

```text
predictive lift : metric(A1) - metric(A0)     (rule value)
                  metric(A2) - metric(A1)     (LLM incremental value over rule)
profit lift     : net(A2) - net(A1)           (via the ledger, V2-02)
LLM cost        : tokens, $ per run, amortized per decision
net LLM value   : profit lift - LLM cost
```

Report lift with a confidence interval (e.g. block-bootstrap over holdout windows). Rule and LLM
arms must be attributable, not conflated.

## Honesty requirements

- If **A2 does not beat A1**, report it plainly and analyze why (event overlap, extraction
  quality, propagation). A null result is a valid, publishable V2 outcome.
- LLM incremental cost is **always** included — a lift that costs more than it earns is reported
  as net-negative.
- "Model-attributed" wording only; no causal claim.
- No fabricated event content to manufacture overlap (base-contract invariant).

## Artifact schema — `reports/v2/llm_value/incremental_value.json`

```jsonc
{
  "run_id": "run_...",
  "arms": {
    "A0_no_event":   { "wape": null, "net": null },
    "A1_rule_event": { "wape": null, "net": null },
    "A2_llm_event":  { "wape": null, "net": null }
  },
  "lift": {
    "rule_over_none":  { "wape_delta": null, "ci": [null, null] },
    "llm_over_rule":   { "wape_delta": null, "ci": [null, null] },
    "profit_llm_over_rule": null
  },
  "llm_cost": { "tokens": null, "usd": null, "usd_per_decision": null },
  "net_llm_value": null,
  "claim_status": "pending"
}
```

## Acceptance

- Three arms separated and reproducible from config.
- Shared cutoffs/splits verified.
- Cost included; net value reported; null results not hidden.
