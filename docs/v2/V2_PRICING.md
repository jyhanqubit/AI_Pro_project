# V2 Dynamic Pricing & Experiment Dry-run (V2-05)

Bounded incentive/pricing policy with hard guardrails, plus an **offline** experiment dry-run.
No real users exist, so pricing outcomes are `simulated` — never a causal business result.

> **Status: implemented + run (V2-05).** Policy `ml/pricing/pricing_v2_eval.py`, runner
> `ml/pricing/pricing_v2_run.py` (`make v2-pricing`). Demand response uses the versioned
> assumption-set elasticity; objective is the V2-02 ledger; bounds/safety rules from
> `config/pricing_v2.py`. Result (576 seeded zone-hours): **0 guardrail violations**, safety zones
> kept at base fare, budget respected (0/40), and a **negative control** confirms the audit catches
> a planted out-of-bounds surge. Sensitivity grid over elasticity × surge-bound, and an **A/A
> switchback dry-run** with effect ≈ 0 / CI covering 0 (design validity, not a treatment effect).
> All `simulated`. 7 tests. Artifacts: `reports/v2/pricing/{guardrail_audit,sensitivity}.json`.

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
