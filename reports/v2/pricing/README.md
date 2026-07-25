# reports/v2/pricing/ — V2-05 Dynamic Pricing & Experiment Dry-run

**Run 2026-07-20.** Reproduce: `make v2-pricing` (offline, seeded). Schema/rules in
`docs/v2/V2_PRICING.md`. Artifacts carry the result envelope, **`claim_status: simulated`** — every
quote is a SIMULATED SHADOW quote, never applied to a rider; no causal/live claim.

Bounded scarcity-surcharge / balancing-credit policy whose demand response is the **versioned
assumption-set elasticity** (`config/v2/assumptions.yaml`) and whose objective is the V2-02 ledger.

## `guardrail_audit.json`

576 zone-hours (seeded scarce/surplus/safety scenario from the V2-04 commute series):

- **Guardrail violations: 0.** Surge ∈ [1.0, 1.5] (G1), credit ∈ [0, 0.25] (G2), no action worse
  than base (G3), total credit spend 0.0 ≤ 40.0 budget (G4), monotone in shortage risk (G5),
  **no surge on SAFETY_INCIDENT zones** (G6, all kept at base fare).
- **Negative control passes**: a planted out-of-bounds surge (9.9×) is correctly flagged by the
  audit — the check has teeth, not a rubber stamp.
- Action mix: 561 base / 15 surge / 0 credit — the policy is conservative, acting only where it
  clearly beats doing nothing (with elasticity −0.3, shedding demand rarely pays), which is the
  guardrail-respecting outcome.

## `sensitivity.json`

- **Elasticity × surge-bound grid**: total net and surge intensity across elasticity {0.5×, 1×, 2×}
  and m_max {1.25, 1.5, 2.0} — shows how the policy responds as the (assumption) elasticity and the
  bound change.
- **A/A experiment dry-run** (switchback, identical policy both arms): estimated effect ≈ 0 with a
  95% CI covering 0 → the estimator is unbiased and the design is valid. This is *design validity*,
  not a treatment effect: there are no real riders, so no causal lift is claimed.
