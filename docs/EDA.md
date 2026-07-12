# Exploratory Data Analysis — JC Citi Bike, June 2026

Source: `JC-202606-citibike-tripdata.csv.zip` (Jersey City / Hoboken), 109,510 valid trips,
40,479 demand cells, 208 H3 res-9 zones, 2026-05-31 .. 2026-06-30. Read-only, offline.
All findings below are measured (scripts in scratchpad, not committed).

## Key findings

### 1. Demand is sharply bimodal on weekdays, unimodal on weekends
- Overall peak is the **evening rush**: 17h = 10,482 departures, 18h = 9,893 (vs 08h = 7,071).
- Weekday average per hour is bimodal (07–08 and 17–18 spikes); **weekend is a midday plateau**
  (10–15h ~230/hr) with much higher late-night activity (00–03h). Commute vs leisure regimes.
- Weekday total > weekend (Tue busiest at 18,142; Sun lowest at 13,690).
- **Implication:** hour-of-day, day-of-week, weekend, and rush flags are all justified (B1).
  The weekend/weekday shape difference means same-hour-**last-week** should beat same-hour-yesterday.

### 2. Lags are strongly predictive; the weekly lag is the best single predictor
Correlation of `departures[t]` with:
| feature | Pearson r | n |
|---|---|---|
| `dep_lag_168` (last week, same hour) | **0.727** | 30,947 |
| `dep_lag_24` (yesterday, same hour) | 0.699 | 39,055 |
| `dep_lag_1` (last hour) | 0.680 | 40,271 |
| `dep_roll_mean_24` | 0.534 | 39,055 |

Confirms the chosen lag set; the weekly lag carries the day-of-week signal implicitly.

### 3. Demand is highly concentrated in a few zones
- Top 20 zones hold **55.5%** of departures; top 50 hold 89.5%. Long tail of tiny zones.
- 63.6% of dense zone-hours have **zero** demand → strong sparsity / zero-inflation.
- **Implication:** a zone-level scale feature (expanding mean) helps the model place a zone.

### 4. Zones have distinct commute polarity
- The busiest zones are strongly **PM-heavy** (top zone: 494 morning vs 3,228 evening departures)
  — transit-hub / workplace behavior. Others are balanced (residential).
- **Implication:** a morning/evening polarity covariate separates zone character (candidate).

### 5. Rebalancing pressure persists
- `corr(net_flow[t], net_flow[t-1]) = 0.440` — hourly imbalance is autocorrelated.
- Over the month most zones are near-balanced, but hourly net flow is the operational signal.
- **Implication:** cumulative same-day net flow captures "how empty/full a zone has become".

### 6. Neighboring zones move together
- `corr(zone dep, mean of H3 grid-disk(1) neighbors, same hour) = 0.453`.
- **Implication:** a spatial-lag feature (neighbor demand) is justified — planned for Phase 05
  alongside the graph `neighbor_zone_impact`.

### 7. The collector currently drops demand-relevant columns
- `rideable_type`: **62% electric / 38% classic**; electric share dips during the AM commute
  (55%) and rises off-peak/late-night (67%).
- `member_casual`: **72% member / 28% casual**. Members drive the weekday commute peaks; casual
  riders drive the weekend leisure plateau — this split likely explains much of finding #1.
- Round trips (same start/end station) 4.3%; trip duration median 6.5 min, p90 18 min.
- **Implication:** capturing `member_casual` (and secondarily `rideable_type`) is the highest-value
  new *raw* signal, but requires a documented contract migration (TripRecord + collector + aggregation).

## Features implemented from this EDA (leakage-safe, in `pipelines/features/lags.py`)

| feature | definition | motivated by |
|---|---|---|
| `dep_momentum`, `arr_momentum` | short trailing mean / long trailing mean (3h/24h) | #2, surge detection for event-awareness |
| `dep_expanding_mean`, `arr_expanding_mean` | running mean of all prior hours (zone scale) | #3 |
| `net_cumsum_day` | net flow accumulated earlier in the same local day | #5 rebalancing pressure |

Feature width: 15 lag/rolling + 10 calendar + 5 EDA-derived = **30**, plus 3 labels.

## Recommended next features (evidence-backed, not yet built)

1. **`member_casual` split** (highest value) — add optional field to `TripRecord`, split demand
   into member/casual counts or a `member_share` feature. Documented migration required.
2. **Spatial neighbor demand** (`neighbor_dep_lag_1`) — H3 grid-disk mean; Phase 05 (with graph
   `neighbor_zone_impact`).
3. **Zone commute polarity** — historical morning/evening ratio as a zone covariate; compute from
   the training window only (Phase 06) to stay leakage-safe.
4. **`rideable_type` electric share** — secondary behavioral signal.
5. **Weather** (rain/heat) — strongest missing exogenous driver; excluded from MVP (§11.2),
   proposed as a post-ablation B5 extension.
