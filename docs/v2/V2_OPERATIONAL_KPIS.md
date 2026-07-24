# V2 운영 KPI — 예측 정확도 밖의 사업 지표

**배경:** WAPE/MASE 같은 forecast metric만으로는 "자산이 잘 쓰이나(사용율)", "탈 자전거가 있나(재고율)",
"수요를 얼마나 충족했나(service level)"를 볼 수 없습니다. CTO 관점에서 필요한 이 운영 KPI를 **source별로
정직하게** 계산합니다. 재현: `make v2-kpi` → `reports/v2/monitoring/operational_kpis.json`.

핵심 규율: 각 KPI를 **어디서 얻는지**에 따라 claim_status를 다르게 답니다.

| KPI | 정의 / 공식 | source | claim_status | 사업 의미 |
|---|---|---|---|---|
| **사용율 (utilization / turnover)** | trips / active_station / day | trip history | **measured** | 자산 효율 — 자전거당 매출. 낮으면 idle 자산 |
| **재고 가용률 (bike availability)** | P(bikes ≥ 1 & renting) | GBFS station_status | demo_fixture → live시 measured | 빌릴 수 있는가 — 낮으면 trip·매출 손실 |
| **품절률 (stockout rate)** | P(bikes == 0) | GBFS station_status | demo_fixture → live시 measured | rebalancing 우선순위(부족). ledger shortage와 직결 |
| **반납 가용률 / 포화률** | P(docks ≥ 1) / P(docks == 0) | GBFS station_status | demo_fixture → live시 measured | 반납 가능한가 — 포화 시 이탈·overflow 비용 |
| **net-flow 불균형 지수** | Σ\|arr−dep\| / Σ(arr+dep) | trip history | **measured** | 구조적 rebalancing 수요의 크기 |
| **service level (충족률)** | realized / (realized + shortage) | ledger | simulated | 핵심 사업 KPI — 충족된 수요 비율 |
| **peak 집중도** | peak-hour trips / total | trip history | **measured** | 첨두 부하 — 재배치·요금 타이밍 근거 |

## 왜 source별로 나누나 (정직성)

- **재고율은 "지금" 값만 measured가 될 수 있다.** GBFS는 실시간 스냅샷만 제공하고 과거 재고 시계열은
  존재하지 않습니다. 그래서 fixture 기반 계산은 `demo_fixture`, 과거 재고율은 `blocked_data`, **라이브
  폴링을 축적하면 그때 measured**가 됩니다. (같은 함수가 mode만 바뀌어 measured가 됨)
- **사용율·불균형은 trip history에서 바로 measured.** 실제 발생한 trip을 집계하므로 가정이 없습니다.
- **service level은 ledger 기반이라 단위는 measured, 금액 가정은 simulated.** (부호·비율은 신뢰 가능)

## 측정 결과 — 실데이터 (NYC 2026 Jan–May, S3 다운로드)

`reports/v2/monitoring/operational_kpis.json` (재현: `make v2-kpi`). trip 부분은 **14,536,837 trips /
152일 / 2,433 stations** 위에서 measured:

| KPI | 값 | claim_status |
|---|---|---|
| 사용율 (trips/station/day) | **39.3** (NYC) · 참고 JC 15.1 | measured |
| daily trips | 95,637 | measured |
| one-way 비율 | **98.1%** | measured |
| net-flow 불균형 지수 | **0.0169** | measured |
| peak-hour share | 9.6% | measured |
| stockout / full (재고, demo fixture 3 stations) | 0.333 / 0.0 | demo_fixture |
| service level — promoted fill_rate / unmet | **0.762 / 0.238** | simulated |

관찰:
- **사용율**: NYC는 station당 하루 **39.3회전**으로 JC(15.1)보다 자산이 훨씬 활발히 쓰임 — 자산 효율 지표.
- **one-way 98%**: 거의 모든 trip이 다른 station에서 끝남 → **구조적으로 재고가 쏠림** = rebalancing 필요의
  근본 원인(net-flow 불균형 지수가 이를 정량화).
- **재고**: 데모 fixture는 station 3개뿐이라 시연용. 라이브 모드에서 stockout_rate·full_rate가 그대로 운영
  알람이 됩니다(같은 함수, mode만 measured로).
- **service level**: promoted 모델이 수요의 **76.2%를 충족**(no-action보다 개선) — 예측 개선이 "충족된 수요"로
  환산되는 지점(핵심 사업 KPI).

## KPI가 이어지는 곳

```text
사용율↓ → idle 자산 (수익성 문제)
재고 품절률↑ / net-flow 불균형↑ → rebalancing 필요 (ledger shortage/overflow 비용)
service level↑ ← 더 나은 forecast → MPC rebalancing → 충족 수요↑ (매출 보호)
```

즉 운영 KPI는 forecast·ledger·rebalancing을 **사업 언어(충족·자산효율·비용)**로 잇는 다리입니다.
