# V2 Dynamic Pricing & Experiment Dry-run (V2-05)

Bounded incentive/pricing policy with hard guardrails, plus an **offline** experiment dry-run.
No real users exist, so pricing outcomes are `simulated` — never a causal business result.

## Policy

- Prices/incentives are bounded: `price ∈ [p_min, p_max]`, incentive `∈ [0, i_max]`.
- Elasticity comes from the versioned assumption set (`config/v2/assumptions.yaml`,
  `claim_status: assumption`). The LLM never computes price numbers directly.
- The policy optimizes the ledger objective subject to guardrails.

## Guardrails (audited)

```text
G1  no price outside [p_min, p_max]
G2  no incentive outside [0, i_max]
G3  no action with negative expected margin
G4  bounded total incentive budget per period
G5  monotonicity sanity: higher shortage risk ⇒ non-decreasing incentive (within bounds)
```

The guardrail audit checks every recommended action against G1–G5 and records violations
(target: zero).

## Experiment dry-run

- Design an A/B or switchback **offline** on fixtures; label results `simulated`.
- Report the design's validity (e.g. A/A CI covering 0) — not a treatment effect on real riders.
- No online learning / bandits (no real user logs → prohibited by base contract).

## Artifact schemas

`reports/v2/pricing/sensitivity.json`:

```jsonc
{
  "run_id": "run_...",
  "assumption_set_version": "v2-assumptions-0",
  "price_grid": [],
  "expected_net_by_price": [],
  "elasticity_used": null,
  "claim_status": "simulated"
}
```

`reports/v2/pricing/guardrail_audit.json`:

```jsonc
{
  "run_id": "run_...",
  "checks": { "G1": null, "G2": null, "G3": null, "G4": null, "G5": null },
  "violations": [],
  "claim_status": "pending"
}
```

## Acceptance

- All recommendations within bounds; guardrail violations = 0.
- Elasticity from versioned assumptions; pricing decisions not made by the LLM.
- Experiment labeled `simulated`; no causal claim.
