# V2-08 — Persistence, Monitoring & Delayed Labels

두 개의 artifact 기반 메커니즘(`make v2-monitor`)이며, 각각 순수 함수로 구성되고 unit test로 검증됩니다
(`tests/unit/test_v2_monitoring.py`).

## 1. Run manifest + freshness monitoring (`ml/monitoring/run_manifest.py`)

모든 `reports/v2/**/*.json` 결과를 스캔하여 `reports/v2/monitoring/run_manifest.json`을 작성합니다. artifact 하나당
한 행으로 `run_id`, `claim_status`, `mode`, `freshness`, `age_hours`, 그리고 `stale` 플래그(> 30 days)를 담습니다.
이는 cockpit / V2-09 audit / 운영자가 모든 결과의 상태와 나이를 확인하기 위해 읽을 수 있는 단일 인덱스입니다.

현재 스캔: **26 artifacts, 모두 `run_id` 보유, 0 stale** — claim_status별로: measured 15,
offline_benchmark 5, simulated 5, blocked_data 1.

**Drift:** live-traffic drift(serving 분포 vs training)는 여기에 없는 live label stream이 필요하므로
`blocked_data`로 보고하며 절대 가짜로 만들지 않습니다. Freshness/staleness와 아래의
delayed-label closure가 실제로 사용 가능한 monitoring 신호입니다.

## 2. Delayed-label loop (`ml/monitoring/delayed_labels.py`) — the leakage guard

미래의 `target_hour`에 대해 `forecast_cutoff`에서 만들어진 live-shadow forecast는 실제 수요가 도착하기 전까지
`pending_live_label` 상태로 유지되며, 도착하면 `measured`로 전환됩니다. 절대 깨져서는 안 되는 규칙
(base-contract §5.2):

> label은 **`label.available_at > forecast.forecast_cutoff`인 경우에만** forecast를 close할 수 있습니다 —
> 그렇지 않으면 채점 시 forecast보다 이전에 존재하던 정보를 사용하게 됩니다(누수, a leak).

availability가 cutoff 이하인 label은 **`leakage_rejected`**이며 forecast는 pending으로
유지됩니다 — 절대 조용히 close되지 않습니다. 이것이 이 phase의 핵심 acceptance("delayed-label backfill이
과거 cutoff로 누수되지 않는다")이며, 정확히-cutoff-지점의 boundary를 포함한 unit test로 검증됩니다.

runner는 `demo_fixture`에서 이 loop를 시연합니다(여기에는 live shadow-forecast stream이 없습니다):
2 pending forecasts + 유효한 delayed label 하나 + 의도적으로 누수되는 label 하나 → **1 closed (measured),
1 leakage-rejected, 1 still pending**. demo 숫자가 아니라 이 메커니즘이 결과물입니다.
실제 close에는 live stream이 필요합니다(여기서는 `blocked`).

## Acceptance status

- Artifacts persisted with run manifests — **done** (`run_manifest.json`).
- Monitoring surfaces freshness — **done**; drift — `blocked_data` (no live labels), 명시됨.
- Delayed-label backfill does not leak into past cutoffs — **done + tested** (strict `>` guard).
