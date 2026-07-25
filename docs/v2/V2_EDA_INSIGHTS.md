# V2 EDA 인사이트 — NYC trip 실데이터

**데이터:** S3에서 내려받은 NYC Citi Bike **2026 Jan–May, 14,536,837 trips / 152일 / 2,433 stations**.
전부 trip 발생 사실만 집계한 **measured** 값(가정 없음). 재현: `make v2-eda` →
`reports/v2/monitoring/eda_nyc.json`. (사용 컬럼: `started_at·ended_at·start/end_station_id·
member_casual·rideable_type·start/end lat·lng`)

---

## 1. 시간 (Temporal)

- **첨두 시간 = 17·18·16시** (저녁 commute). hour-of-day share: 아침 8시 6.7% vs **저녁 17시 9.6%** —
  **bimodal이되 PM이 AM보다 ~43% 큼**. 새벽 3–4시는 0.3%.
- **주중 중심**: weekend_share **24.8%**. 요일별(Mon→Sun) 0.129 / 0.154 / 0.154 / 0.155 / **0.161(금)** /
  0.133 / **0.115(일)** — 금요일 최고, 일요일 최저.
- **월별 급증**: Jan 1.82M → Feb 1.22M → Mar 2.95M → Apr 3.86M → **May 4.69M**. 겨울→봄으로 **약 2.6배**
  성장(계절성).

**인사이트:** 수요는 commute 주도(평일 저녁 첨두)이고 계절 성장이 매우 크다. → (a) 재배치·인력은 **오후
첨두**에 집중, (b) **월별 성장**이 커서 학습 구간(train window)이 최근일수록 데이터가 몰림 — 이것이 앞서
borough lift가 train 3개월에서 inconclusive였다가 4개월에서 유의해진 이유와 정합(최근 월의 데이터량이 큼).

## 2. 공간 (Spatial) — 재배치의 핵심

- **불균형 지수: 전 기간 합산 0.017 vs hour 단위 0.154 (약 9배)**. 장기적으로는 도착≈출발이지만,
  **station×시간대 단위로 보면 순 15%가 한쪽으로 쏠린다.**
- one-way 비율 **98.1%** — 거의 모든 대여가 다른 station에서 반납.
- artifact에 상위 출발 station / 순유입(sink) / 순유출(source) station 목록 포함.

**인사이트(가장 중요):** **rebalancing은 '단기(시간대)' 문제다.** 전 기간 지표(1.7%)만 보면 "균형 잡혀 있다"고
오판하지만, hour 단위(15.4%)가 진짜 운영 부하다. 출근 시간 주거지역은 순유출, 업무지역은 순유입 →
**시간대별 순흐름**이 재배치 방향·규모를 정한다. (period 지표는 rebalancing 필요를 **9배 과소평가**)

## 3. Trip 특성

- **소요시간 평균 12.0분.** 버킷: 0–5분 3.44M · 5–10분 4.83M · 10–20분 4.11M · 20–45분 1.88M · 45+ 0.26M
  → **약 57%가 10분 이내**의 짧은 이동.
- **직선거리 평균 1.96 km.** 버킷: <0.5km 1.40M · 0.5–1km 3.12M · 1–2km 4.84M · 2–5km 4.27M · 5km+ 0.84M.

**인사이트:** 대부분 **short last-mile/commute hop**(≤2km, ≤10분). → 촘촘한 dock 밀도와 짧은 회전이 핵심이고,
장거리 요금 정책보다 **밀집 지역 재고 확보**가 서비스 레벨을 좌우.

## 4. 이용자 · 자산 (Users / Assets)

- **member 85.2% / casual 14.8%.** casual의 **33.4%가 주말**(전체 주말 24.8%보다 높음) → casual = 레저/관광,
  member = commute.
- **e-bike 72.2%** — 이미 전기자전거가 다수.

**인사이트:** (a) 안정 매출은 member commute, **성장 여지는 casual 주말·관광** 세그먼트(요금·프로모 타깃).
(b) e-bike 비중이 높아 **충전·배터리 재배치**가 별도 운영 변수. (c) 요금/재배치 정책을 세그먼트별로 나눌 근거.

## 5. 모델링 함의

- 수요는 sparse count + **강한 hour·요일·월 seasonality** → lag/calendar feature가 지배적이라는 기존 결론과 정합.
- **월별 성장(2.6배)** 때문에 rolling-origin 평가에서 **train 구간 길이가 성능·유의성에 민감** — event lift
  같은 미세 효과는 충분한 최근 데이터가 있어야 드러난다.
- net-flow **hour 단위 불균형(0.154)** 이 rebalancing/MPC의 실제 최적화 대상 → KPI도 hour 단위로 봐야 함.

---

## 6. 공간·OD·세그먼트 심화 (backlog 1·2·3·6, measured)

`make v2-eda-spatial` → `reports/v2/monitoring/eda_spatial.json`. H3는 역(station) 단위로만 매핑(1,550
H3 zone, res 9).

### H3 zone × 시간대 순흐름 (backlog 1) — 재배치의 직접 신호

`net_in = 유입(arrivals) − 유출(departures)`. 가장 큰 신호(절댓값순):

| H3 zone | 시각 | net_in | flow |
|---|---|---|---|
| `892a100d2…` | **08시** | **+7,040** (순유입) | 14,622 |
| `892a100d6…` | 17시 | −6,382 (순유출) | 10,074 |
| `892a100d2…` | 17–18시 | −5,097 / −5,391 | ~15k |

**핵심 인사이트 — commute reversal:** 같은 zone(`892a100d2`)이 **아침 8시엔 순유입(+7,040)**, **저녁 17–18시엔
순유출(−5,097/−5,391)**. 즉 업무지구 zone이 아침에 자전거로 차고 저녁에 빈다. → **아침에 쌓인 zone에서 저녁
피크 전에 자전거를 빼 주거지역으로 보내는 시간대별 재배치 경로**가 데이터로 직접 나온다. (period 지표로는 절대
안 보이는 신호)

### OD corridor (backlog 2)

- 최다 왕복 hotspot: `6912.01`↔동일 station **4,232건** (공원·레저형 왕복).
- top 순불균형 corridor(편도 쏠림): `6072.06→6072.11` net **+1,283**, `6753.08→6822.09` +859 등 — 특정 축으로
  한 방향 쏠림 = **재배치 트럭 우선 경로**.

### 세그먼트: member/casual × e-bike/classic (backlog 3)

| 세그먼트 | share | 평균 소요 | 평균 거리 |
|---|---|---|---|
| member · e-bike | **60.8%** | 11.0분 | 2.09km |
| member · classic | 24.4% | 11.0분 | 1.52km |
| casual · e-bike | 11.4% | **17.0분** | 2.23km |
| casual · classic | 3.4% | **20.5분** | 1.94km |

**인사이트:** casual은 소요시간이 member의 **1.5–2배**(17–20분, 레저성), member는 11분(commute). e-bike가
거리 약간 김. → 시간제 요금·casual 타깃 프로모의 근거.

### 요일 × 시간 (backlog 6)

- **평일 peak 17시(퇴근) vs 주말 peak 15시(오후 레저)** — commute↔leisure 전환이 요일별 첨두 이동으로 확인.
- 요일 share: 금요일 최다(16.1%), 일요일 최소(11.5%).

---

## 추가로 할 EDA (backlog)

| # | 항목 | 왜 | 상태 |
|---|---|---|---|
| 1 | **H3 zone 단위 시간대별 순흐름** | 재배치 경로/우선순위 도출 | ✅ 완료 (§6) |
| 2 | **OD corridor top-N + 순불균형** | 주요 이동 축·불균형 축 | ✅ 완료 (§6) |
| 3 | **member/casual × e-bike/classic 교차** | 세그먼트별 이용 행태 | ✅ 완료 (§6) |
| 6 | **요일×시간 heatmap** | 재배치 스케줄 근거 | ✅ 완료 (§6) |
| 4 | **station capacity 대비 dock 회전율** | 병목 dock 식별 | ⏳ GBFS capacity/live 필요 |
| 5 | **event/날씨 window와 수요 이상치 정렬** | 이상 탐지·설명(news followup 연결) | ⏳ 이벤트/날씨 join 필요 |
| 7 | **첨두 집중도의 계절 변화(월별)** | 재배치 스케줄 계절 조정 | ⏳ 다음 단계(현 데이터로 가능) |

§6에서 1·2·3·6을 measured로 완료. 4·5는 외부 데이터(GBFS live / event·weather join) 필요.

_수치 재현: `reports/v2/monitoring/eda_nyc.json`(§1–5) · `reports/v2/monitoring/eda_spatial.json`(§6). 전부 measured._
