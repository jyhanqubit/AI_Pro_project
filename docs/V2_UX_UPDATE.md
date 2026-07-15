# V2 — Usability Update (UI, Search, Operator Analytics)

_Last updated: 2026-07-15_

This is a **usability-focused, backward-compatible** increment on top of V1. It does not introduce
any new modelling, pricing, or experiment claims: every number is computed offline from the same
pipeline the v1 API already uses, and the demand delta stays labelled as the `demo-heuristic-v1`
demo heuristic (Historical Replay), never a measured Phase 06 model output (CLAUDE.md §§3, 13, 22).

## Goals

1. **Rider UI that reads like a consumer bike-share app** — search-first, at-a-glance availability,
   tap-to-detail — instead of a raw card grid.
2. **Search** — find a station by Korean / English name, district, or alias (typo-tolerant).
3. **Stronger operator statistics / analytics** — real aggregate KPIs and distributions of the
   as-of replay state.

## What shipped

### 1. Rider home redesign — `apps/web/app/page.tsx`

- A prominent, pill-shaped **search bar** (`지역 검색 — 예: 시청, 호보켄, Grove, 뉴포트`).
- An availability summary as **filter chips**: `전체` / `빌리기 좋아요` / `곧 부족`.
- A clean **station list** (rows, not a grid): Korean + English name, district, a capacity gauge,
  the live bike count, an availability pill (넉넉 / 여유 / 빠듯 / 곧 부족), free docks, and a 🔥 surge
  badge when an event is raising demand in that zone.
- A tap-to-open **station detail sheet** (bottom sheet on mobile, centered dialog on desktop):
  bikes / free docks / capacity, an availability advice line, and — when the zone is event-exposed —
  the demand shift (`baseline → event-aware /시간`, e.g. `9.3 → 13.2 +3.9`) with a
  "이 지역이 붐비는 이유 보기 →" link into the existing Why-Changed trace.

Search filtering is instant/client-side over the fetched list; the list itself comes from the V2
search endpoint below.

### 2. Station search — `GET /v2/rider/stations/search`

- Params: `q` (query, empty returns all), `k` (max hits, default 20).
- Matching is a case-insensitive **substring** over the station's names / district / aliases from
  `data/fixtures/station_gazetteer.json` (static place metadata — Korean, English, and aliases like
  `waterfront`, `path`, `터미널`). Empty query returns all stations **ranked by availability**.
- Each hit is **hydrated with the as-of live inventory** from the operational fixture (bikes,
  capacity, free docks, target, shortage/surplus, availability level, and the zone's demand delta).
  The inventory is never inferred from the query text (CLAUDE.md V2 invariant: Elasticsearch/search
  is not the source of truth for inventory — here the "search index" is the gazetteer and the store
  is the rebalancing fixture).
- Respects the leakage boundary: before an event's `available_at`, its zone's `demand_delta` is `0`.

### 3. Operator statistics — `GET /v2/operator/statistics` + `apps/web/app/statistics/page.tsx`

Real aggregations of the as-of replay state (all reconcile with the v1 endpoints):

- **System inventory**: total bikes / capacity, system utilization, total free docks.
- **Availability distribution**: station counts by level (rendered as a stacked bar + legend).
- **Shortage load**: stations in shortage, total shortage units, total surplus units.
- **Event mix**: available event count, counts by demand effect (increase / decrease / unknown) and
  by event type (rendered as a bar list).
- **Demand-delta spread**: total Δ, max |Δ|, mean Δ over affected zones; top-surge zones.
- **Per-zone breakdown**: bikes / capacity, utilization, baseline vs. event-aware forecast, Δ, event
  exposure, worst availability level (rendered as a sortable-by-Δ table).

The new operator screen is reachable from the nav as **운영 통계**. Changing the replay cutoff at the
top recomputes every metric as-of the new boundary.

### 4. Event-window timeline — `GET /v2/operator/timeline`

A time-series strengthening of the operator analytics: for every hourly cutoff across the demo
window (12:00 → 18:00) the **same offline pipeline is recomputed as-of that boundary**, yielding an
honest series of `event_count`, `affected_zone_count`, `total_shortage_units`, `stations_in_shortage`,
and `demand_delta_total` — plus `event_markers` at each event's `available_at`.

- Rendered on `/statistics` as two self-contained **SVG area+line charts** (부족 재고 units and
  수요 Δ 합계 /시간) sharing the hour axis, with dashed vertical **event-onset markers** and an event
  legend. No chart library — plain inline SVG.
- The series demonstrates the leakage boundary visually: it is flat (0 shortage, 0 Δ) until the
  first event's onset, then rises and eases with the event window. Station inventory is a static
  fixture, so utilization is flat by design; the shortage / Δ / event series are what move.
- `event_count` is monotonically non-decreasing (as-of availability only accumulates), asserted in
  tests.

### 5. Optimal extra-bike allocation — `POST /v2/operator/rebalancing/allocate`

Answers the operator question *"the system has N bikes now; I want to inject M more — how should I
distribute them for the biggest benefit?"* (M is an operator input). This complements the existing
relocation solver (which conserves the total): here we **add** bikes.

- **Optimizer** (`optimization/classical/allocation.py`): distributes M bikes to minimise the same
  asymmetric operational cost (shortage 3 : overflow 1, `config/rebalancing.py`) subject to hard
  constraints — `added_i ≥ 0` integer, `bikes_i + added_i ≤ capacity_i`, `Σ added_i ≤ M`. Because
  the objective is **separable and convex**, a greedy that places each bike where its marginal
  benefit is largest is **globally optimal**; `allocate_brute_force` validates greedy == exhaustive
  optimum in tests (mirrors the QUBO validation pattern, §14.2).
- **Honest by construction**: a bike is placed only while it strictly reduces cost (fills a
  shortage). Once every station is at target, further bikes would only add overflow, so they are
  reported as **held back in the depot** (`leftover`) rather than force-placed to inflate a number.
- **UI**: a "추가 자전거 최적 분배" card at the top of `/rebalancing` with a numeric input for M and a
  result view — current total, optimally placed vs. held-back, shortage before→after, operating
  benefit (cost reduction), and a per-station table highlighting where bikes go. Recomputes as-of
  when the replay cutoff changes (targets rise with events). Response fields include `extra_requested`,
  `placed`, `leftover`, `shortage_units_before/after`, `overflow_units_before/after`,
  `cost_before/after`, `benefit`, and the per-station `added`.

## Files

| Area | File | Change |
| --- | --- | --- |
| Fixture | `data/fixtures/station_gazetteer.json` | **new** — rider-facing place metadata + aliases |
| Config | `config/collectors.py` | `STATION_GAZETTEER_FIXTURE` path |
| API | `services/api/v2.py` | **new** — `station_search`, `operator_statistics`, `operator_timeline`, `allocate_extra_bikes`, shared views |
| API | `services/api/app.py` | wire `/v2/rider/stations/search`, `/v2/operator/statistics`, `/v2/operator/timeline`, `/v2/operator/rebalancing/allocate` |
| API | `services/api/schemas.py` | `ExtraBikeAllocationRequest` |
| Opt | `optimization/classical/allocation.py` | **new** — optimal extra-bike allocator + brute-force oracle |
| Web | `apps/web/app/rebalancing/page.tsx` | `추가 자전거 최적 분배` planner (operator M input) |
| Web | `apps/web/lib/api.ts` | typed client: `StationHit`, `OperatorStatistics`, methods |
| Web | `apps/web/app/page.tsx` | rider home redesign (search + chips + list + detail sheet) |
| Web | `apps/web/app/statistics/page.tsx` | **new** — operator analytics screen |
| Web | `apps/web/components/Nav.tsx` | add `운영 통계` tab |
| Web | `apps/web/app/globals.css` | search bar, chips, station rows, sheet, stat widgets |
| Tests | `tests/integration/test_api_v2.py` | **new** — 9 integration tests |

## Reproduce

```bash
# Backend (offline, no API key)
make api                       # serves the v1 + v2 endpoints on :8000

curl "127.0.0.1:8000/v2/rider/stations/search?q=시청"
curl "127.0.0.1:8000/v2/operator/statistics"
curl "127.0.0.1:8000/v2/operator/timeline"
curl -X POST "127.0.0.1:8000/v2/operator/rebalancing/allocate" \
  -H 'Content-Type: application/json' -d '{"extra_bikes": 8}'

# Frontend
make web                       # Next.js dev server on :3000  ->  /  and  /statistics

# Tests
python -m pytest tests/integration/test_api_v2.py -q
cd apps/web && npm run typecheck && npm run build
```

## Honesty / invariants

- No fabricated metrics: statistics are pure aggregations of the offline state; the demand delta is
  the labelled demo heuristic, not a measured model.
- As-of correctness preserved: search and statistics both derive demand deltas from
  `engine.forecasts(cutoff)`, so an event contributes nothing before its `available_at`.
- Search index ≠ source of truth: hits are re-hydrated from the operational fixture.
- Fully offline and deterministic; no network in tests.
