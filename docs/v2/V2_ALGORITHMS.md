# V2 알고리즘 — 원리와 Metric

각 알고리즘이 **어떻게 동작하는지(원리)** 와 **어떻게 측정하는지(metric)** 를 한곳에 정리한 문서입니다.
여기 나오는 모든 metric은 코드에 정의돼 있고, 모든 대표 수치는 `reports/v2/**` 아래 committed artifact가
재현합니다 (`reports/v2/final/claim_matrix.json`이 각 claim을 artifact에 연결). 공식은
`ml/forecasting/metrics.py`, `ml/forecasting/llm_feature_value.py`, `optimization/`, `ml/copilot/`의
구현과 일치합니다.

목차:
1. 공통 forecasting metric (WAPE / MAE / MASE / OCS)
2. 수요 예측 모델 (Seasonal-Naive → HistGradientBoosting; A0/A1/A2 ablation)
3. LLM Feature Value — LLM feature가 정확도를 실제로 개선했는가?
4. Profit / Regret ledger
5. 재배치 decisioning — No-Action / Greedy / MILP / MPC / Oracle
6. 강화학습 (research) — tabular Q-learning & PPO
7. Dynamic pricing (simulated)
8. Decision Copilot — typed-tool grounding, GraphRAG retrieval, RAGAS

---

## 1. 공통 forecasting metric

모든 error metric은 **H3 zone × local-hour** grain에서, leakage 없는 as-of holdout 위에서 계산합니다.

> 도메인 용어: **H3 zone** = Uber의 육각 격자(hexagonal grid), 이 프로젝트는 res 9(한 칸 ≈170 m, 동네
> 몇 블록 크기)를 사용. **borough** = 뉴욕시 자치구(시 행정구역, Manhattan 등 5개, H3보다 훨씬 거친 단위).

| Metric | 공식 | 쓰는 이유 | Zero-denominator 규칙 |
|---|---|---|---|
| **MAE** | `mean(|y − ŷ|)` | 자전거 대수 단위의 절대 오차 | 비어 있으면 `NaN` |
| **WAPE** | `Σ|y − ŷ| / Σ|y|` | scale-free, cell별 0이 많은 sparse zone에 robust | 오차도 0이면 `0`, 아니면 `NaN` |
| **MASE** | `MAE(model) / MAE(seasonal-naive, in-sample)` | naive **대비** skill — `<1`이면 naive를 이김 | scale이 0/NaN이면 `NaN` |
| **OCS** | `(c_short·under + c_over·over) / Σy` | 비대칭 운영 비용 (stockout ≠ overflow) | WAPE와 동일; `c_short=c_over`면 WAPE와 같음 |

- **MASE의 scale**은 seasonal-naive(`y_t` vs `y_{t−period}`)의 in-sample MAE이고, `period = 168 h`(주간)를
  씁니다. **training** history에서만 계산합니다(`seasonal_naive_scale`).
- 수요가 sparse하고 heavy-tail이라 **WAPE를 대표값**으로 씁니다. cell별 MAPE는 0에 가까운 cell로 나눠서
  터집니다. 코드: `ml/forecasting/metrics.py`.

---

## 2. 수요 예측 모델

**원리 — 복잡도 순서대로 쌓되, 각 단계를 leakage test로 gate합니다** (base contract §11.1). LLM은 수요를
직접 예측하지 않고, **feature만** 만듭니다.

| 모델 | 원리 | 역할 |
|---|---|---|
| **B0 Seasonal-Naive** | `ŷ_t = y_{t−168h}` (지난주 같은 시간) | 정직성의 바닥; MASE 분모이기도 함 |
| **Global tree (promoted)** | lag/rolling/calendar feature 위의 `HistGradientBoosting`, 전 zone 공통 단일 모델 | 실제 서빙 모델 |
| **Event-aware** | 위 tree + LLM/graph event feature (§3) | 검증 대상 |

**Promoted 모델** (`reports/v2/holdout/promoted_model.json`): `hist_gradient_boosting`,
`lr=0.05, depth=8, iters=600`. Promotion = H3 multi-holdout에서 이긴 config이고, non-demo API가 서빙하는
artifact입니다(`ml/forecasting/promoted.py`). demo heuristic이 아닙니다.

**H3 multi-holdout** (`reports/v2/holdout/h3_multiholdout.json`): **rolling-origin** 방식으로 **3개 expanding
window** 평가입니다 (random K-fold는 미래를 leak시키므로 절대 금지). 각 window는 cutoff까지 학습하고 다음
블록을 test합니다. 측정값: **WAPE 0.4828 ± 0.0030, MASE 0.7996 ± 0.0186** (MASE < 1이면 seasonal-naive를
이김; naive는 WAPE ≈ 0.648).

**Feature ablation** (§3의 실험 무대):

```
A0  demand history + calendar          (event 없음)
A1  A0 + structured event feed (permit, count)
A2  A1 + LLM-from-news event feature
```

모든 ablation 단계는 **동일한 cutoff와 split window**를 씁니다 (contract §5.4). 그래야 WAPE 차이가 split이
아니라 추가한 feature 덕분이라고 말할 수 있습니다.

---

## 3. LLM Feature Value (LFV) — 판정용 metric

**답하는 질문:** *feature layer를 추가했을 때 예측 정확도가 의미 있게 좋아졌는가?* — 느낌이 아니라 재현
가능한 판정으로 답합니다. 정의: `ml/forecasting/llm_feature_value.py`.

**원리:**
1. WAPE를 **LLM-active subset**(해당 feature가 실제로 켜지는 zone-hour)에서만 계산합니다. 수백만 개의
   비활성 cell에 delta를 희석하면 진짜 효과가 묻힙니다.
   `skill = (WAPE_without − WAPE_with) / WAPE_without` (상대 WAPE 감소, `+`면 개선).
2. active subset을 **block-bootstrap**(autocorrelation을 보존하는 연속 time block)해서 skill의 95% CI를
   구합니다.
3. **판정 규칙(사후 튜닝 아님, 사전 선언):** 두 gate를 모두 통과해야 함 —
   `|skill| ≥ rel_threshold (0.01)` **그리고** CI가 0을 배제. 아니면 null입니다.

```
skill ≥ +0.01 이고 CI>0   → MEANINGFUL_POSITIVE
skill ≤ −0.01 이고 CI<0   → MEANINGFUL_NEGATIVE
그 외                      → NO_MEANINGFUL_EFFECT
(active support < min_active=100)  → INSUFFICIENT_SUPPORT
```

**Metric = `(decision, skill, CI, n_active)` 튜플.** 승리만큼이나 null도 그대로 보고합니다 — 개선이 없는
모델도 정직한 1급 결과입니다 (contract §11.4). 순수 함수이고 unit test 6개.

**측정 결과 (V2-03 핵심 발견):**
- Structured event feed (A1−A0): nowcast에서 **`MEANINGFUL_POSITIVE +2.69%`** — event는 도움이 됨.
- LLM-from-news (A2−A1): net **negative / null** — news는 structured feed 대비 redundant.
- Root cause (가정이 아니라 증명): feature가 도움이 되려면 source가 **dense + precise-time +
  precise-location + forward-looking** 이어야 함. news는 하나도 만족 못 함 (23개 event 중 forward-looking은
  2개뿐). Synthetic ceiling (`synthetic_ceiling.json`, *simulated*)은 4가지를 모두 만족하는 source를 주입 →
  **+10.43%**. 즉 *방법 자체는 동작*하고 real-news의 null은 **source의 한계**입니다. 전체 정리:
  `docs/v2/V2_WHY_LLM_FEATURES.md`.

---

## 4. Profit / Regret ledger

**원리** (`optimization/ledger.py`, contract는 `contracts/v2/ledger.py`): 예측의 정확도를 **versioned
assumption set**(`config/v2/assumptions.yaml`)을 통해 금액으로 환산합니다.

```
contribution_margin = margin_per_rental · realized_rentals
shortage_cost       = shortage_externality · unmet_demand_units      (externality이지 lost margin 아님)
overflow_cost       = overflow_penalty · overflow_units
relocation_cost     = reposition_cost_per_unit · moved_units
net = contribution_margin − shortage_cost − overflow_cost − relocation_cost
regret_vs_oracle = Oracle_net − policy_net        (구조상 ≥ 0)
```

**Integrity 규칙:** margin은 *realized* rental만 셈. shortage는 unmet demand에 대한 **externality**이고 lost
margin으로 **이중 계산하지 않음**. 모든 금액 항은 `claim_status: simulated`(assumption에 조건부)이고, 단위
수량만 `measured`. dollar claim 전에 assumption grid를 **sensitivity sweep**해서 부호가 안정적인지 확인해야
합니다.

**Metric:** `net`(높을수록 좋음), `regret_vs_oracle`(낮을수록 좋음).
측정값 (`reports/v2/ledger/profit_regret.json`): promoted forecast가 114,079 zone-hour에서 seasonal-naive
대비 **+$103,271** net; **9개 cost 설정 모두에서 부호가 양수**.

---

## 5. 재배치 decisioning — policy scoreboard

모든 policy는 같은 seeded commute 시나리오에서 **동일한 V2-02 ledger**로, 같은 feasibility solver로 채점됩니다.
**Oracle**은 realized demand를 써서 offline **upper bound**가 되므로 모든 policy의 `regret_vs_oracle ≥ 0`.
Artifact: `reports/v2/mpc/policy_comparison.json` (`simulated`).

| Policy | 원리 |
|---|---|
| **No-Action** | 아무것도 안 옮김 — do-nothing 바닥 |
| **Greedy** | 매 시간 가장 넘치는 zone에서 가장 빈 zone으로, local하게 균형 맞을 때까지 옮김 |
| **MILP** (single-period) | mixed-integer program: capacity + vehicle 제약 + non-negative integer move 하에서 이번 시간 ledger cost 최소화 |
| **MPC** | receding horizon: **H-step forecast**로 각 zone의 target을 정함 `target = clip(cap/2 − Σ_H forecast_net, 0, cap)`, 같은 MILP로 그쪽으로 이동, 한 스텝 실행, 반복 |
| **Oracle** | forecast 자리에 *realized* demand를 넣은 MILP — 배포 가능한 policy가 아니라 offline bound |

**필수 제약 (전부 강제, infeasibility는 명시적으로 보고):** zone이 가진 것보다 많이 못 옮김, 목적지 capacity
초과 금지, non-negative integer move, vehicle capacity 준수.

**Metric:** ledger `total_cost`(낮을수록 좋음), `regret_vs_oracle`.
측정값: NoAction 1127 / Greedy 1155 / MILP 1087 / **MPC 740** / Oracle 719 → **MPC가 best feasible,
regret 21.6 (Oracle의 ~3%)**, 전부 feasible.

---

## 6. 강화학습 (Research Mode 전용)

RL은 **research 전용**이고 V2 completion 조건이 **아닙니다** (addendum). §5 scoreboard에 *learned-control*
baseline을 하나 더 추가하되, 동일한 ledger + eval 시나리오로 측정합니다. **RL advantage는 주장하지 않습니다**
("no quantum advantage" 규칙과 동일). 전체 문서: `docs/v2/V2_RESEARCH_RL.md`. 두 learner 모두 **순수 numpy**
(torch 없음), 완전히 seeded, offline (online/bandit 학습 없음).

### 6a. Tabular Q-learning (`optimization/rl/qlearning.py`)

**원리 — sampled transition 위의 model-free value iteration.** `Q(s,a)`(미래 (음의) cost 기댓값)를
temporal-difference update로 학습:

```
Q(s,a) ← Q(s,a) + α · [ r + γ · max_a' Q(s',a') − Q(s,a) ]
```

ε-greedy exploration(선형 decay). greedy policy는 `argmax_a Q(s,a)`.
- **State** (72개): `(hour_of_day, system_imbalance_bucket ∈ {−,0,+})` — coarse, *global*.
- **Action** (15개): *global* target-shaping control `(α ∈ {0..2}, H ∈ {1,3,6})`. 이 규칙이 built-in policy를
  포함함 — `α=0`은 No-Action, **`α=1,H=6`은 MPC** — 즉 MPC가 자기 action 중 하나임.

### 6b. PPO (`optimization/rl/ppo.py`)

**원리 — trust region이 있는 policy-gradient.** stochastic policy `π_θ(a|s)`(diagonal-Gaussian MLP,
action은 `[0,1]`로 clip)를 **clipped surrogate**를 올려서 직접 최적화:

```
r_t(θ) = π_θ(a_t|s_t) / π_θ_old(a_t|s_t)
L = E[ min( r_t · Â_t ,  clip(r_t, 1−ε, 1+ε) · Â_t ) ]  +  entropy bonus  −  value loss
```

- Advantage `Â_t`는 **GAE(λ)**로: `δ_t = r_t + γV(s_{t+1}) − V(s_t)`, `Â_t = Σ (γλ)^l δ_{t+l}`.
- 별도 MLP **critic** `V(s)`를 return에 MSE로 학습; 전체 param에 **Adam**(manual backprop).
- **State** (`2·z+2`): **zone별** `[inventory/cap, Σ_H forecast/cap]` + clock — MPC가 쓰는 정보. **Action**:
  **zone별** continuous target fraction. 이걸로 tabular의 state/action 병목을 제거함.

### Metric & 결과 (`reports/v2/research/rl_rebalancing.json`)

§5와 동일: held-out `seed=42` 시나리오에서 ledger `total_cost` / `regret_vs_oracle`. 단, **training은 서로
다른 seed**로 함 (eval noise는 절대 학습에 안 넣음 — forecaster와 같은 leakage 규율). Verdict field:
`best_rl`, `ppo_beats_tabular`, `beats_mpc`.

| policy | regret vs Oracle |
|---|---:|
| oracle | 0.0 |
| **mpc** | **21.6** |
| rl_ppo | 202.9 |
| rl_qlearning | 247.8 |
| milp / no_action / greedy | 368 / 408 / 436 |

**해석:** PPO(더 풍부한 representation)가 tabular Q-learning을 이김 (202.9 < 247.8) — 점수를 제약한 건
*representation*이지 알고리즘이 아니었음을 확인. 둘 다 MPC에는 못 미침. MPC의 Oracle 대비 gap은 **대부분
줄일 수 없는 forecast noise**이기 때문 (Oracle은 realized demand를 보지만 learner는 못 봄). RL advantage는
주장하지 않음.

---

## 7. Dynamic pricing (simulated)

**원리** (`ml/pricing/`, 문서 `docs/v2/V2_PRICING.md`): 안전한 base fare 위에 **bounded** surge/discount를
얹고, forecast imbalance로 구동하되 강한 **guardrail**(최대 multiplier, budget cap, 보호 floor)과 라이브 테스트
전 설계 검증용 **A/A dry-run**을 둡니다. Elasticity는 **versioned assumption**이고, 모든 quote는 **shadow**
(실제 청구 안 함).

**Metric** (`reports/v2/pricing/{sensitivity,guardrail_audit}.json`, `simulated`): guardrail 위반 수(반드시
**0**), budget 준수, 통과해야 하는 **negative control**, **A/A CI가 0을 포함**(유효한 null 설계). 측정값:
**576 zone-hour에서 위반 0건**, negative control 통과, A/A CI가 0 포함.

---

## 8. Decision Copilot — grounding & retrieval

LLM은 **오직** event structuring, tool routing, explanation에만 씀 — 숫자 계산에는 **절대** 안 씀. typed tool
결과가 뒤에 없는 numeric answer는 reject (addendum "LLM Boundaries"). 문서: `docs/v2/V2_GRAPHRAG_COPILOT.md`.

| 구성요소 | 원리 | Metric | 결과 |
|---|---|---|---|
| **Typed-tool routing** | NL 질문 → typed tool 호출 → tool의 numeric 결과만 숫자의 유일한 출처 | routing accuracy + **numeric-hallucination 수** | 20 Q: real-Claude routing **1.0/1.0/1.0**, **halluc = 0** (keyword baseline은 3개 hallucinate → fail) |
| **GraphRAG retrieval** | as-of event graph에서 evidence event 검색; 답이 그걸 cite | gold set 대비 precision / recall | *graph-구조적* task에서는 GraphRAG 21/21이지만 이건 **구조상** 높음 |
| **Neutral text-lookup control** | method-independent gold, plain text 검색 | top-1 accuracy | flat_text **0.833**이 graph_boosted 0.750을 **이김** — degree-boost는 text에 도움 없음; *질문 유형에 tool을 맞춰라* |
| **RAGAS retrieval** | real `ragas` 0.4.3 **non-LLM** metric | context-precision / recall | flat 0.833 vs graph 0.771 (recall 동률) — control과 일치 |
| **RAGAS generation** | faithfulness = 답의 모든 claim이 retrieved context에 근거; answer-relevancy | faithfulness / answer_relevancy | **faithfulness 1.0**, **answer_relevancy 0.985** (답한 10 Q; in-session 판정 + verdict commit + drift-guard) |
| **Trip-plan faithfulness** | rider plan 숫자(distance/time)는 반드시 typed plan에 있는 값이어야 함 | grounded-number 비율 | **1.0**, ungrounded 0; negative control("999") 잡아냄 |

**정직한 프레이밍:** GraphRAG가 항상 나은 게 아님 — 질문이 graph 모양일 때만 이김. neutral control + RAGAS가
양쪽으로 verdict를 bound하는 게 핵심.

---

## 각 알고리즘이 어디에 나타날 수 있나 (mode / claim 규율)

| 알고리즘 | claim_status | Product surface? |
|---|---|---|
| Promoted forecaster, H3 holdout, LFV, structured-event lift | `measured` | 예 (non-demo) |
| Copilot benchmark, trip faithfulness | `offline_benchmark` | 예 (offline) |
| Ledger, MPC, pricing | `simulated` | 비교용, 라벨 붙여서만 |
| Synthetic ceiling | `simulated` | research/분석 전용 |
| **RL (Q-learning, PPO)** | `research` | **절대 안 됨** — `ResultEnvelope`가 차단 |

이 규율은 `ResultEnvelope` validator(`contracts/v2/envelope.py`)가 코드로 강제하고, final audit
(`make v2-final`)이 committed artifact마다 다시 검증합니다.
