# Data Contracts (as built)

Typed contracts at every service/pipeline boundary (CLAUDE.md §6). All are Pydantic v2 models on
a strict base (`contracts/common.py`: `extra="forbid"`, whitespace-stripped) so contract drift
fails loudly. All datetimes are timezone-aware (`AwareDatetime`, §5.1). Enumerations live in
`contracts/enums.py`.

## Enumerations

- `OperatingMode` — `demo_fixture | historical_replay | live | research`.
- `EventType` — `TRANSIT_DISRUPTION | WEATHER_SHOCK | LARGE_VENUE_EVENT | ROAD_CLOSURE |
  PUBLIC_GATHERING | SAFETY_INCIDENT | SYSTEM_ALERT | OTHER`.
- `EffectDirection` — `increase | decrease | unknown`.
- `ExtractionStatus` — `accepted | rejected | quarantined`.
- `TargetName` — `departures | arrivals | net_flow`.
- `RiderType` — `member | casual`.

## `TripRecord` (`contracts/trip.py`)

`trip_id`, `started_at`, `ended_at`, `start_station_id`, `end_station_id`, `start_lat`,
`start_lng`, `end_lat`, `end_lng`, `source_file`, `loaded_at`, `rider_type?`. Coordinates are
range-validated; the collector reports (does not silently drop) missing coordinates, reversed
times, implausible durations, and duplicates, recording excluded counts and reasons in metadata.

## `ArticleRecord` (`contracts/article.py`)

`article_id`, `title`, `text` (full text or permitted snippet only), `source`, `published_at`,
`first_seen_at`, `available_at?` (= `max(published_at, first_seen_at)`), `url_hash`, `mode`,
`raw_payload_path`. Replayed strictly by `available_at`; deduped on `article_id` / `url_hash`.

## `EventExtraction` (`contracts/event.py`)

`event_id`, `source_article_ids[]`, `event_type`, `event_title`, `event_summary`, `published_at`,
`first_seen_at`, `available_at?`, `event_start_at?`, `event_end_at?`, `locations[]`
(`Location{name, lat?, lng?, h3_zone?}`), `demand_effect`, `capacity_effect`, `severity`
(bounded prior), `confidence`, `evidence_spans[]` (`EvidenceSpan{article_id, text, start_char?,
end_char?}`), `extraction_model`, `extraction_prompt_version`, `status`. Every accepted event has
provenance and **non-empty, text-grounded evidence spans** (§4, §8). Rejected/quarantined events
are kept (auditable).

## `StationStatusRecord` (`contracts/station.py`)

`station_id`, `num_bikes_available`, `num_docks_available`, `is_installed`, `is_renting`,
`is_returning`, `last_reported?`, and provenance `source_last_updated`, `fetched_at`,
`payload_hash`, `raw_payload_path`, `mode` (§7.3).

## `DemandCell` (`contracts/demand.py`)

`zone_id` (H3), `hour_start` (local-hour, tz-aware), `departures`, `arrivals`,
`net_flow = arrivals − departures`, `departures_member`, `departures_casual`, `mode`. The primary
grain is **H3 zone × local hour** (§4).

## `FeatureSnapshot` (`contracts/feature.py`)

`zone_id`, `forecast_cutoff`, `feature_version`, `source_event_ids[]`, `features: dict[str,float]`,
`created_at`. Each snapshot traces its numeric features back to source events; deterministic input
+ cutoff + config → identical output (§10).

## `ForecastOutput` (`contracts/forecast.py`)

`zone_id`, `forecast_cutoff`, `forecast_horizon`, `model_version`, `feature_version`,
`target_name`, `baseline_forecast`, `p10?/p50?/p90?` (omitted/null when no calibrated interval,
§6.5 — intervals are never invented), `event_aware_forecast`, `forecast_delta?`, `mode`.

## API models (`services/api/schemas.py`)

Request/response models for §12 endpoints mirror the contracts above and always carry mode and,
where relevant, cutoff and model/feature versions. Explanations always include provenance and
evidence (never evidence-free). Rebalancing adds `RebalancingRequest` (`cutoff?`, `method`,
`vehicle_capacity?`) and `RebalancingResponse` (feasibility + reason, moves, per-station
before→after inventory, shortage/overflow reduction, costs) — see [OPTIMIZATION.md](OPTIMIZATION.md).

## Rebalancing model (`optimization/classical/problem.py`)

Internal (non-Pydantic) dataclasses: `Station(station_id, name, lat, lng, bikes, capacity,
target, zone_id?)` with inventory invariants; `Move(origin_id, destination_id, quantity,
distance_km)`; `RebalancingProblem(stations, costs, vehicle_capacity)`;
`RebalancingPlan(moves, solver)`. Cost weights are typed config (`config/rebalancing.py`).
