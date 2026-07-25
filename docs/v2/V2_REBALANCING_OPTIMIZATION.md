# 재배치 최적화 — 정식화 · 제약 · 풀이의 어려움

ShockFlow AI의 rebalancing(차량 재배치) 최적화를 **수식 수준**으로 정리한 문서. 목적함수(최소화 식),
제약 조건, 그리고 실제로 이 문제를 푸는 것이 왜 어려운지를 다룬다. 구현: `optimization/classical/`
(`problem.py`·`objective.py`·`milp.py`·`ortools_solver.py`·`greedy.py`·`enumeration.py`),
receding-horizon 확장은 `optimization/mpc.py`.

---

## 1. 문제 정의 (single-period)

한 시점에서, 각 station의 현재 재고를 **target 재고**에 맞추도록 자전거를 옮기되, 이동 비용과 미달/초과
비용의 합을 최소화한다.

**집합 / 인덱스**
- station $i \in \{1,\dots,n\}$
- 순서쌍 $(i,j),\ i \ne j$ (i에서 j로의 이동)

**파라미터 (station별, 정수)**

| 기호 | 의미 |
|---|---|
| $b_i$ | 현재 재고 (bikes) |
| $C_i$ | capacity (dock 수) |
| $t_i$ | target 재고 (forecast로 정함) |
| $d_{ij}$ | station i↔j 직선거리(km, haversine) |
| $V$ | 차량 용량(한 번에 옮길 수 있는 총 대수), 기본 18 |
| $c_s, c_o, c_d$ | shortage / overflow / distance 단위 비용 = **3.0 / 1.0 / 0.5** |

invariant: $0 \le b_i \le C_i$, $0 \le t_i \le C_i$ (모두 비음 정수).

**결정 변수**
- $x_{ij} \in \mathbb{Z}_{\ge 0}$ : i→j로 옮기는 자전거 수, $0 \le x_{ij} \le \min(b_i, V)$
- $s_i \ge 0$ : shortage (target 미달분)
- $o_i \ge 0$ : overflow (target 초과분)

**파생량**
$$\text{out}_i = \sum_{j \ne i} x_{ij}, \quad \text{in}_i = \sum_{j \ne i} x_{ji}, \quad f_i = b_i - \text{out}_i + \text{in}_i$$
($f_i$ = 재배치 후 최종 재고)

---

## 2. 목적함수 (최소화)

$$
\min_{x,s,o}\;\; \underbrace{c_d \sum_{i \ne j} d_{ij}\, x_{ij}}_{\text{이동(relocation) 비용}}
\;+\; \underbrace{c_s \sum_i s_i}_{\text{shortage 비용}}
\;+\; \underbrace{c_o \sum_i o_i}_{\text{overflow 비용}}
$$

**비대칭성(핵심):** $c_s = 3 > c_o = 1$ — **품절(빌릴 자전거 없음)을 dock 초과보다 3배 무겁게** 둔다. 품절은
trip·매출·신뢰 손실이라 더 아프기 때문. (예측 metric의 OCS와 같은 비대칭 철학.)

---

## 3. 제약 조건

모든 station $i$에 대해:

$$
\begin{aligned}
&\text{(1) 출발지 재고}      && \text{out}_i \le b_i \\
&\text{(2) 물리적 재고 범위} && 0 \le f_i \le C_i \\
&\text{(3) shortage 선형화}  && s_i \ge t_i - f_i \\
&\text{(4) overflow 선형화}  && o_i \ge f_i - t_i \\
\end{aligned}
$$

전역:
$$
\text{(5) 차량 용량}\quad \sum_{i \ne j} x_{ij} \le V, \qquad
\text{(6) 정수성}\quad x_{ij} \in \mathbb{Z}_{\ge 0}
$$

**선형화가 맞는 이유:** $s_i, o_i$ 는 목적함수에서 **양의 비용**을 가지므로, 최적해에서는 하한에 딱 붙는다 —
$s_i = \max(0,\, t_i - f_i)$, $o_i = \max(0,\, f_i - t_i)$. 즉 절댓값/`max`를 LP로 정확히 표현한다
(`objective.plan_cost`가 계산하는 값과 동일).

**feasibility 규칙(§14.1):** 출발지 재고 초과·목적지 capacity 초과·음수/비정수 이동·차량 용량 초과는
명시적으로 금지되고, 위반 시 사람이 읽는 사유를 반환한다. 계획은 이 검사를 통과해야만 노출된다.

---

## 4. 어떻게 푸나 (solver 사다리)

| solver | 무엇 | 성질 |
|---|---|---|
| **Greedy** (`greedy.py`) | 한계이익 큰 surplus→deficit 이동 반복 | 항상 feasible, do-nothing 이하. **최적 보장 X** |
| **MILP** (`milp.py`) | 위 식을 `scipy.optimize.milp`(HiGHS)로 정확해 | **exact optimum**. 실패 시 enumeration으로 degrade |
| **Enumeration** (`enumeration.py`) | 소규모 완전열거 | MILP·QUBO의 독립 정답 대조(search-space cap) |
| **OR-Tools** (`ortools_solver.py`, optional) | 동일 MILP를 CBC로 | MILP·enumeration과 **동일 최적해** 검증됨 |
| **QUBO/QAOA** (`quantum/`, research) | 소규모를 QUBO로 매핑 | 완전열거와 에너지 일치 검증. 양자 우위 주장 X |

검증된 관계(테스트): `greedy ≤ do-nothing`, **`MILP cost == enumeration cost == OR-Tools cost`**(모두 최적),
차량 용량 준수.

---

## 5. 실제 풀이의 어려움

이 문제는 "작으면 쉽고, 현실 규모·현실 조건에선 어렵다". 정직하게 정리한다.

### 5.1 규모 — 변수 폭발
$n$개 station이면 flow 변수가 $n(n-1)$개. NYC 실데이터는 **station ≈ 2,433개 → $x_{ij}$ ≈ 590만 개**.
전 네트워크를 한 번에 MILP로 푸는 것은 비현실적. 그래서:
- enumeration은 **search-space cap**으로 소규모에만,
- MILP도 surplus→deficit 엣지로 **슬라이스**를 제한,
- MPC 시뮬레이터는 **zone 축약(8 zones)** 위에서 per-period로 푼다.
실배포는 **borough/H3 cluster 단위 분해**나 column generation이 필요(현재 미구현).

### 5.2 정수성 — NP-hard
MILP는 일반적으로 NP-hard(branch-and-bound 최악 지수). 순수 transportation 문제라면 제약행렬이
totally unimodular라 LP 완화만으로 정수해가 나오지만, **차량 용량 결합 제약 (5)** 와 비대칭 비용이 붙어
순수 transportation이 아니다 → 정수성이 실제로 문제될 수 있다(소규모·구조적 instance는 빨리 풀림).

### 5.3 비대칭·축퇴(degenerate) 비용
$c_s \gg c_o$ 라 **동일 비용의 최적해가 여러 개** 나온다. solver마다 (똑같이 최적인) 다른 계획을 반환할 수
있어, 우리는 **계획 identity가 아니라 total_cost로 검증**한다. 또 distance 비용이 float이라 CP-SAT처럼
정수 목적함수를 요구하는 solver는 **비용 스케일링**이 필요(그래서 기본은 float를 그대로 받는 CBC/HiGHS).

### 5.4 시간 결합 — 진짜 어려운 부분
single-period MILP은 "지금 한 번"만 본다. 실제 수요는 연속적으로 흐르고(§EDA: 같은 zone이 아침 순유입·저녁
순유출), 최적 재배치는 **multi-period inventory routing** 문제다 — static transportation MILP보다 훨씬 어렵다.
MPC는 receding-horizon으로 근사하지만 **완전한 동적 최적을 푸는 것은 아니다**(정직한 범위 한계).

### 5.5 라우팅 미모델링
$x_{ij}$ = "i→j로 q대"는 **트럭의 실제 경로**(여러 station을 순회 — capacitated VRP)를 추상화한다. 우리 모델은
flow 기반이지 route 기반이 아니다. 현실 운영은 이 위에 **VRP(vehicle routing)** 가 한 겹 더 필요하다.

### 5.6 forecast 불확실성
$t_i$(target)는 예측에서 온다 — 최적화는 **target이 정확한 만큼만** 좋다. 불확실성을 다루려면 stochastic
programming / CVaR 같은 robust 변형이 필요(현재는 deterministic; SP/CVaR은 optional).

### 5.7 데이터 messiness (실측에서 실제로 겪음)
실 station id·좌표에 `NA`·범위 밖 값이 섞여 있어(EDA 재실행 중 확인) 모델을 세우기 전에 **정제**가 필수.
불량 입력은 스킵하거나 enumeration으로 degrade하고, **가짜 계획을 만들지 않는다**(§22).

---

## 6. 정직한 범위 요약

| 우리가 실제로 푸는 것 | 완전한 현실 문제 |
|---|---|
| single-period, flow 기반 MILP (zone 축약/슬라이스) | multi-period **stochastic inventory routing + VRP** |
| deterministic target | forecast 불확실성(robust/stochastic) |
| exact optimum(소규모) · MPC 근사(동적) | 대규모 동적 최적 (분해·근사 필요) |

즉 **정식화와 최적성은 검증됐고**(MILP=enumeration=OR-Tools), 어려움은 대부분 **규모·시간 결합·라우팅·
불확실성**에 있다. 다음 고도화 후보: cluster 분해, VRP 결합, stochastic/CVaR target, 대규모 warm-start.
