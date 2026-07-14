# V1-08 — Clustered-Switchback Experimentation (SIMULATED)

> **SIMULATED OUTCOME — NOT A LIVE BUSINESS RESULT / NOT A CAUSAL LIFT.** There are no real users,
> so outcomes come from the V1-07D choice simulator and effects are simulated ITT contrasts, never a
> real causal lift (V1_Prompt §17, invariants 9/10). Reproduce: `make v1-experiment-dry-run`.

## Design

- **Randomisation unit = zone-cluster × time-block** (clustered switchback), respecting
  shared-inventory interference. The demo network is small, so each cluster is a **replicate market**
  of the full 5-station scenario with cluster-specific demand; policies act on a whole market.
- **Balanced switchback**: each cluster alternates arms with a balanced starting phase, so within
  every time block the arms are split 50/50 → propensity 0.5, no temporal confound.
- Washout: leading block dropped. Analysis: **ITT** with a **cluster block-bootstrap 95% CI**
  (clusters are the resampling unit) + **CUPED** variance reduction on a P0 pre-period covariate.
  **SRM** check on arm shares. Status: `simulated_experiment`.

## Battery (seed 42, 4 clusters × 10 blocks)

| Experiment | ITT | 95% CI | CUPED ITT | SRM |
|------------|-----|--------|-----------|-----|
| **A/A** (identical arms) | +0.025 | [−0.015, +0.065] | 0.000 | ok |
| Recommendation-only vs no action | +0.056 | [+0.021, +0.091] | +0.033 | ok |
| Static vs event-aware dynamic credit | +0.078 | [+0.046, +0.113] | +0.055 | ok |
| Hybrid (truck+rec+dynamic) vs no action | +0.103 | [+0.078, +0.131] | +0.084 | ok |

Metric = simulated fulfilled-demand rate.

## Reading (simulated only)

- **A/A validation passes**: the CI contains 0, so the design does not manufacture a false positive.
  This is the gate that makes the treatment readouts trustworthy *within the simulation*.
- Treatments show ordered, detectable simulated effects (hybrid > dynamic-credit > recommendation-
  only), consistent with the V1-07D policy comparison. CUPED shrinks the estimate toward the
  covariate-adjusted signal.
- **These are simulated ITT contrasts, not causal lifts.** A real causal claim requires a real
  randomized experiment with real users (`config/v1/claims.yaml::experiment_claim`); until then the
  status stays `simulated_experiment` and no lift is claimed in the portfolio.

## Tested (`tests/unit/test_experiment.py`)

Deterministic clustering/assignment; balanced assignment (no SRM); **A/A CI contains 0**; a
treatment shows a CI excluding 0; every result labelled `simulated_experiment` with the disclaimer;
exposure/outcome logs recorded with propensity 0.5; exactly-two-arms guard; recommendation-only arm.
