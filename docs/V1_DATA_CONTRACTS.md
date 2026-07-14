# ShockFlow AI V1 — Data Contracts

All V1 contracts live in `contracts/v1/` and extend the strict `ContractModel` base
(`extra="forbid"`, timezone-aware datetimes). They are additive to the v0 contracts.

## Enums (`contracts/v1/enums.py`)

- `OperatingModeV1` — `demo_fixture, historical_replay, live_shadow, policy_simulation, experiment_dry_run, research` (superset of v0's 4).
- `ClaimState` — `measured, pending, simulated, dry_run, research`.
- `RecommendationMode` — `rent, return`.
- `AnomalyType` — `data_quality, inventory, forecast_residual, proxy_demand`.
- `RootCauseStatus` — `explained_by_event, partially_explained, unexplained, likely_data_quality, inventory_dislocation`.
- `ReasonCode` — recommendation explanations (reason codes, not attention weights).

## Records

| Contract | File | Purpose | Key invariants |
|----------|------|---------|----------------|
| `ArticleRecord` | `records.py` | Backfilled news article | `available_at >= max(published_at, first_seen_at)`; url/title hashes for dedup |
| `EventRecordV1` | `records.py` | Extracted event | non-empty `evidence_spans`; `severity/confidence ∈ [0,1]`; no numeric demand %; `event_end_at >= event_start_at` |
| `ForecastPair` | `forecasting.py` | M0/M1/M1-zero as-of one cutoff | `event_delta = M1 − M1-zero` (model-attributed, not causal); quantile ordering; carries versions+seed+`claim_state` |
| `ScoredForecastPair` | `forecasting.py` | Pair + realised label | `MEASURED` ⇒ non-null `actual`; `actual` ⇒ `label_source`; label is never GBFS delta |
| `AnomalyAlert` | `anomaly.py` | Anomaly + root cause | `is_synthetic_fault` explicit; evidence trace fields |
| `RecommendationRequest` | `recommendation.py` | RENT/RETURN query | `query_is_synthetic` flag; radius/detour bounds |
| `RecommendationResult` | `recommendation.py` | Ranked stations | infeasible removed (not penalised); `no_feasible_candidate` ⇒ empty list; component scores kept separate |
| `IncentiveQuote` | `recommendation.py` | Pickup/return credit | `is_simulated=true` + disclaimer by default; credit ≥ 0 |
| `ExperimentDefinition` | `experiment.py` | Switchback design | `randomization_unit = zone_cluster × time_block`; `status ∈ {actual, simulated, dry_run}` |
| `ExposureLog` / `OutcomeLog` | `experiment.py` | Assignment / outcome | outcome `is_simulated` default true |

## Claim-state placement

`ForecastPair`, `AnomalyAlert`, `RecommendationResult` each require a `ClaimState`. This makes the
measured / pending / simulated / dry-run boundary a **schema-enforced** property, not a UI
convention (V1_Prompt §6 acceptance).

## Migration note

No v0 field is renamed or removed. Any future breaking change requires a documented migration entry
here plus a compatibility test (invariant 12).
