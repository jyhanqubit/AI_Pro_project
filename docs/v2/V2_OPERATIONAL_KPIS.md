# V2 운영 KPI (measured only)

예측 metric(WAPE/MASE)만으로는 "자산이 얼마나 쓰이나(사용율)", "어떻게 쓰이나(편도·첨두·회원·e-bike)"를
못 본다. 이 문서는 **trip history에서 measured로만** 계산한 운영 KPI를 담는다. 가정(cost/elasticity)이나
실시간 스냅샷에 의존하는 지표(재고율=GBFS demo, service level=ledger simulated)는 **제외**했다.
재현: `make v2-kpi` → `reports/v2/monitoring/operational_kpis.json`.

## 입력 데이터

- source: S3에서 내려받은 **NYC 2026 Jan–May trip** (git-ignored, `make download-citibike`).
- Citi Bike CSV는 13개 컬럼. KPI에 쓰는 건 **5개**: `started_at`, `start_station_id`,
  `end_station_id`, `member_casual`, `rideable_type`. (나머지 `ride_id`/`ended_at`/`*_name`/
  `*_lat`/`*_lng`는 미사용 — 위경도는 H3 매핑용.)
- 규모: **14,536,837 trips / 152일 / 2,433 stations**. pandas 청크 스트리밍(전량 메모리 적재 안 함).

## 측정 결과 (measured)

| KPI | 값 | 공식 | 계산법 |
|---|---|---|---|
| **사용율 (turnover)** | **39.3** trips/station/day | trips / active_station / day | 14,536,837 / 2,433 / 152 |
| daily trips | **95,637** | trips / day | 14,536,837 / 152 |
| **one-way 비율** | **98.1%** | P(start ≠ end) | 대여≠반납 건수 / 총 trip |
| net-flow 불균형 지수 | **0.017** | Σ\|arr−dep\| / Σ(arr+dep) | station별 도착·출발 카운트 합산 |
| peak-hour | **17시**, share **9.6%** | peak-hour trips / total | `started_at` 시(hour) 히스토그램 최댓값 |
| member 비율 | **85.2%** | P(member_casual==member) | member 건수 / 총 trip |
| e-bike 비율 | **72.2%** | P(rideable_type==electric_bike) | electric_bike 건수 / 총 trip |

모두 "trip이 실제로 일어났다"는 사실만 세므로 **가정 0 → measured**.

## 해석 (사업 의미)

- **사용율 39.3회전/일** — station 하나가 하루 39번 쓰임. 자산 효율의 직접 지표(자전거당 매출). 낮으면 idle.
- **one-way 98%** — 거의 모든 이용이 편도 → 출발·도착이 구조적으로 어긋남 = **rebalancing이 필요한 근본 원인**.
- **net-flow 불균형 0.017 (caveat)** — 이 값은 **5개월 전 기간 합산**이라 "장기적으론 도착≈출발"을 뜻함.
  정작 rebalancing을 강제하는 **시간대별 단기 쏠림**은 장기 합산에 묻히므로, 운영 관점에선 **hour 단위로
  다시 계산**해야 정확하다. (one-way 98%가 그 단기 쏠림의 간접 증거.)
- **peak 17시 · 9.6%** — 저녁 러시에 이용이 집중 → 재배치·요금 타이밍 설계 근거.
- **member 85% / e-bike 72%** — 구독 이용이 대다수(안정 매출), 전기자전거가 주력(요금·충전·재배치에 영향).

## 왜 재고율·service level은 뺐나

- **재고율(stockout/fill 등)**: GBFS `station_status`는 *실시간 스냅샷*만 제공 → 과거 재고 시계열이 없어
  measured 불가(`blocked_data`). 라이브 폴링을 축적하면 그때 measured가 된다.
- **service level(충족률)**: ledger의 *가정 기반*(cost/elasticity) 수요·부족에서 나오는 `simulated` 값.

두 지표는 measured가 아니므로 이 문서/artifact에서 제외했다.
