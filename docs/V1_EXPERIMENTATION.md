# ShockFlow AI V1 — Experimentation

> Status: **design defined (V1-00).** Only simulated / dry-run experiments are implemented until
> real users exist (V1-08).

## 1. Model comparison is NOT a randomized experiment

This distinction is a hard rule (invariant 9, V1_Prompt §6 acceptance):

| | **Model / forecast comparison** | **Randomized experiment (A/B / switchback)** |
|---|---|---|
| Question | Which model predicts better on a fixed holdout? | Does deploying a policy *cause* a business outcome change? |
| Unit | zone-hour rows (observational) | randomised **zone-cluster × time-block** |
| Assignment | none — same data scored by each model | deterministic randomised assignment + exposure log |
| Output | WAPE/MAE/MASE, event-lift | ITT effect with CIs, propensity |
| Valid claim | "M1 has lower holdout error" | "policy caused Δ" — **only** with real users |
| Never say | — | do not call a model comparison an A/B test |

An offline forecast ablation (`B0..B4`, `R0..R4`) is a **comparison**, never an experiment.

## 2. Design (V1-08)

- Randomisation unit = **zone cluster × time block** (clustered switchback) to respect shared-inventory
  interference.
- Deterministic clustering/assignment; A/A validation; washout; stratification.
- Exposure / outcome / propensity logging (`ExposureLog`, `OutcomeLog`).
- SRM check; ITT analysis; cluster/time-block uncertainty; CUPED or pre-period adjustment.
- IPS/DR only when propensity is logged.

## 3. Result labelling

Every result returns exactly one of `actual_experiment | simulated_experiment | experiment_dry_run`
(`ExperimentDefinition.status`). Without real users, only `simulated_experiment` / `experiment_dry_run`
are produced, and outcomes carry `is_simulated=true`. A **causal lift** claim is allowed only for a
real randomized experiment with real users (`config/v1/claims.yaml::experiment_claim`).

## 4. First experiment order

`A/A → recommendation-only → static vs dynamic credit → hybrid policy` (all simulated/dry-run until
real interaction logs exist).
