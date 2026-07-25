# V2 Claims Matrix & Result Envelope

모든 V2 API 응답과 UI 지표는 아티팩트로 추적 가능해야 하며 라벨링되어야 한다. 이
문서는 **result envelope** 를 정의하고 **claim matrix** (현재 전부 `pending`) 를 담는다.

## Result envelope

노출되는 모든 결과 — forecast, ledger 수치, policy 비교, pricing 추천,
Copilot 답변 — 는 다음을 함께 지닌다:

```jsonc
{
  "value": 0.0,                 // the number/string being claimed (or null if unavailable)
  "run_id": "run_...",          // the execution that produced it
  "artifact_id": "reports/v2/.../file.json#pointer",  // where it is persisted
  "mode": "demo_fixture",       // demo_fixture | historical_replay | live | research
  "claim_status": "pending_live_label",
  "freshness": "2026-07-20T00:00:00Z"  // when the backing artifact was produced (tz-aware)
}
```

규칙:
- `artifact_id` 가 없는 숫자 값은 non-demo 모드에서 렌더링할 수 없다.
- `mode` 와 `claim_status` 는 독립적이다: `historical_replay` 결과도 `measured` 일 수 있고,
  `live` 결과는 지연 라벨이 도착하기 전까지 `pending_live_label` 일 수 있다.
- `demo_fixture` 휴리스틱은 `claim_status: demo_fixture` 로 설정할 수 있으며
  `live`/`historical_replay`/`research` 표면에는 절대 나타나서는 안 된다.

## `claim_status` taxonomy

| status | meaning | may drive product decision? |
|---|---|---|
| `measured` | 실제 데이터에 대한 실제 holdout/experiment 로 생산됨 | yes |
| `offline_benchmark` | 고정된 offline benchmark 집합에서 측정됨 | yes (offline) |
| `simulated` | 실사용자 없는 model/policy 시뮬레이션 | 비교용, causal 결과로는 불가 |
| `pending_live_label` | 지연된 ground-truth 라벨 대기 중 | pending 으로 표시 |
| `assumption` | 버전 관리된 assumption set (cost/elasticity) 유래 | 입력값으로, 라벨링하여 |
| `blocked_data` | 필요한 데이터가 아직 수집/게이팅되지 않음 | blocked 로 표시, 숫자 위조 금지 |
| `blocked_external` | 외부 의존성 이용 불가 (rate-limit, key) | blocked 로 표시 |
| `demo_fixture` | 결정적 demo 휴리스틱 | demo 모드 전용 |
| `research` | research 전용 (RL/QAOA/etc.) | 제품 표면에 절대 공급 안 됨 |

## Claim matrix (current)

> 모든 행은 담당 phase 가 실제 아티팩트를 생산하기 전까지 `pending` 이다. v1 숫자나 추정치로
> 셀을 채우지 말 것 — 오직 `reports/v2/**` 에서만 채울 것.

| Claim | Phase | Artifact (target) | claim_status | Value |
|---|---|---|---|---|
| Promoted measured model artifact 가 존재하며 serving 을 위해 로드 가능 | V2-01 | `reports/v2/holdout/promoted_model.json` | **measured** | `hist_gradient_boosting` (lr=0.05, depth=8, iters=600), `ml/forecasting/promoted.py` 통해 served; API 연결 → V2-07 |
| H3 multi-holdout WAPE (aggregate, 3 rolling windows, JC 2024) | V2-01 | `reports/v2/holdout/h3_multiholdout.json` | **measured** | WAPE **0.4828 ± 0.0030**, MASE **0.7996 ± 0.0186**, B0 ~0.648 를 능가 |
| 구조화된 event feed lift (permitted) | V2-03 | `reports/v2/llm_value/incremental_value_borough.json` | **measured** | Borough/NYC 19.9M trips, test May: A1−A0 WAPE 0.1069→0.1047, CI [1.87,5.88], +$33k — 구조화된 events 가 도움됨 (v1 재현) |
| LLM-from-news incremental value | V2-03 | `reports/v2/llm_value/incremental_value_borough.json` | **measured (negative)** | 실제 Claude extraction (23 clean NYC events, 336 test rows), test May: A2−A1 WAPE 0.0883→0.0905, CI [−5.32,−1.56], **net LLM value −$17,789**. 고품질 LLM extraction 에서도 net-negative — news 는 구조화된 feed 대비 중복이며, mock 아티팩트가 아님 |
| **LLM Feature Value metric** (LLM features 가 정확도를 향상시켰는가?) | V2-03 | `reports/v2/llm_value/incremental_value_borough.json#llm_feature_value_metric` | **measured** | 의사결정 등급 지표 = **LLM-active subset** 에 대한 상대 WAPE 감소 + block-bootstrap CI. 기존 flat-box feature: **`MEANINGFUL_NEGATIVE`**, −5.52%, CI [−17.51, −0.98], n=336 → 측정 가능하게 성능 저하. 사전 선언 임계값 (1% effect + CI≠0); pure fn, 6 unit tests |
| 개선된 LLM feature + graph contribution | V2-03 | `reports/v2/llm_value/graph_contribution.json` | **measured (null)** | feature engineering 수정 (event-time anchor, half-life decay, type-scoped boroughs). 개선된 feature A2−A1: **`NO_MEANINGFUL_EFFECT`** −0.4%, CI [−4.90,1.36] — **harm 제거됨** (기존 −5.52%), 이제 중립. Graph A3−A2: **`NO_MEANINGFUL_EFFECT`** −1.32%, CI [−3.76,0.72] — **graph 는 borough grain 에서 입증되지 않음** (coarse: 5 zones). 공정한 시험대는 H3-zone grain 이며 아직 실행 안 됨. 거짓 양성 아님 |
| "News→permit-DB" 재구성 | V2-03 | `reports/v2/llm_value/permitize_contribution.json` | **measured (hypothesis refuted)** | LLM 이 news 를 permit-schema 레코드로 재구성 (정밀 time+borough). permitized−A1 **`MEANINGFUL_NEGATIVE` −6.31%** CI [−25.2,−5.5]; raw news 보다도 나쁨. **구조가 빠진 재료가 아님** — permit feed 의 가치는 event DENSITY (63,070 events) 이며 news 의 ~19 대비. 희소 event 에 대한 정밀 feature = 확신에 찬 noise. 4 events 는 leakage 로 drop (retrospective). negative |
| permit feed 에 대한 News-as-importance-weight | V2-03 | `reports/v2/llm_value/importance_weight_contribution.json` | **measured (negative)** | ev_active×(1+news_salience) — dense permit feed 를 변조, news 없는 곳은 그대로. **`MEANINGFUL_NEGATIVE` −7.82%** CI [−25.6,−5.9] (WAPE 0.0883→0.0925). 대표 사례: Winter Storm Fern 이 permit 63→119.7 로 증폭하나, 눈보라는 수요를 억제 → 부호가 틀림. "Newsworthy" ≠ "수요 증가"; 부호가 이질적, ~191 rows 학습 불가 |
| H3-grain graph contribution (공정한 시험대) | V2-03 | — | **blocked_data** | 세밀한 H3 graph 시험은 geocoded events 가 필요; 실제 permit/news events 는 borough-tagged 만 가능 (lat/lng 없음; geocoding 은 외부 데이터 필요). 위조 아님. Borough-grain graph 시험 (null) 이 실제 데이터로 가능한 가장 세밀한 공정 시험 |
| Signed LLM demand signal (LLM 유래 방향) | V2-03 | `reports/v2/llm_value/signed_demand_contribution.json` | **measured (neutral, understood)** | LLM `demand_effect∈[−1,+1]` (blizzard −0.9, festival +0.5, LIRR shutdown +0.6). **LLM sign-correctness 0.77** (방향은 맞음!), harm 제거됨 (−7.82%→−2.04%), 그러나 **`NO_MEANINGFUL_EFFECT`** CI [−7.26,+1.44]. 이유: autoregressive lags 가 이미 진행 중 event 수요를 인코딩 → news signal **중복**. 이유를 완성: sparsity + sign + redundancy |
| Post-processing correction (per-mechanism factors) | V2-03 | `reports/v2/llm_value/postprocess_contribution.json` | **measured (negative)** | model output 을 `pred + Σα_ch·signal_ch` 로 보정, per-mechanism α 는 train 에서 calibrated. **`MEANINGFUL_NEGATIVE` −21.36%** CI [−102.6,−4.95] (WAPE 0.0883→0.0899). 적합된 factor 가 터무니없거나 부호가 틀림 (α[gather]=−470, α[transit]=−478) → 희소 calibration 이 **overfit**, test 에서 실패. Sparsity 가 model 에서 post-proc 로 이동; 여전히 ~19 events 로 안정적 factor 를 고정 불가 |
| Forecast-horizon sweep (event value 대 lead time) | V2-03 | `reports/v2/llm_value/horizon_contribution.json` | **measured** | 긴 horizon 에서 최근 lags 를 잃으면 events 가 더 중요해지는지 시험. Permit A1−A0 는 nowcast (h=1) 에서만 `MEANINGFUL_POSITIVE` **+2.69%**; h≥6 에서는 중립 (baseline WAPE 가 두 배 → noise 증가). News 는 모든 horizon 에서 neutral-to-negative. 이 null 은 nowcasting 아티팩트가 **아님** |
| **Root-cause: density curve + quality ablation** | V2-03 | `reports/v2/llm_value/{density_curve,quality_ablation}.json` | **measured** | 단순 sparsity 문제가 아님을 증명. Density curve: permit value 는 news-scale (≤100 events; news~19) 에서 죽어있고, ≥300 에서 나타나나 non-monotonic → density 는 필요조건이지 충분조건 아님. Quality ablation (density 를 FULL 로 유지): exact-time (−0.33%), exact-borough (+0.53%), forward-timing (+1.01%) 각각을 저하시키면 +2.69% 가 붕괴. 원인 = dense+precise-time+precise-location+forward-looking 의 결합; news 는 넷 다 실패; "더 많은 데이터" 는 density 만 해결 |
| News condition audit (news 가 4가지를 충족 가능한가?) | V2-03 | `reports/v2/llm_value/news_condition_audit.json` | **measured** | 23 news events 중 forward-looking 은 2, forward+precise 둘 다는 1 (June, test 밖). 충족 subset 이 거의 비어있는 이유는 news 가 본질적으로 coincident/retrospective 하기 때문 — 4-D 인코딩은 원본에 없는 정보를 추가할 수 없음 |
| Synthetic ceiling — post-correction 역량 | V2-03 | `reports/v2/llm_value/synthetic_ceiling.json` | **simulated** | forward-looking 정밀 dense event shock 을 실제 수요에 주입한 것을 공개. LLM post-correction **+10.43% MEANINGFUL_POS** (feature +20.86%); news-scale density → INSUFFICIENT. 방법/post-correction 이 좋은 events 를 활용 가능함을 증명 (real-news null 은 SOURCE 문제). real-news 주장이 아님 |
| 실제 permit feed 에 대한 LLM enrichment (path A) | V2-03 | `reports/v2/llm_value/{permit_enrich,permit_typed}_contribution.json` | **measured (negative)** | 실제 forward-looking permit feed (4가지 조건 모두 충족) 에서, 조잡한 count 를 넘는 LLM semantic 구조화는 도움 안 됨: 부과된 demand-direction **−3.39%**, factual type-buckets **−1.9%** (둘 다 crude count 대비 MEANINGFUL_NEGATIVE). Aggregate count 가 borough grain 에서의 상한; 더 세밀한 구조는 overfit / per-H3 grain 필요 (blocked: permits 는 borough-tagged). 이 데이터에서 LLM demand value = count 를 넘지 않음 |
| LLM incremental cost | V2-03 | `reports/v2/llm_value/incremental_value.json` | **measured** (mock $0) + **assumption** (est real) | actual $0 (mock); est real $0.0061/371 articles; net LLM value −$0.01 |
| Predictive lift → profit/regret | V2-02 | `reports/v2/ledger/profit_regret.json` | **simulated** ($ assumption-conditioned; units measured) | Promoted forecast 가 114,079 zone-hours 에 걸쳐 seasonal-naive 대비 **+$103,271** 순이익; 부호는 9개 cost setting 전부에서 positive; regret vs Oracle $218,697 |
| MPC vs No-Action/Greedy/MILP | V2-04 | `reports/v2/mpc/policy_comparison.json` | **simulated** | Ledger cost (낮을수록 좋음): NoAction 1127 / Greedy 1155 / MILP 1087 / **MPC 740** / Oracle 719. MPC 가 최선의 feasible, regret 21.6 (Oracle 의 ~3%); 전부 feasible |
| Pricing sensitivity + guardrail audit | V2-05 | `reports/v2/pricing/{guardrail_audit,sensitivity}.json` | **simulated** | 576 zone-hours: guardrail 위반 0, safety base-fare, budget 준수, negative control 통과; A/A CI 가 0 을 포함 (design 유효). Shadow quotes 만 |
| Copilot correctness + relevance | V2-06 | `reports/v2/copilot/{correctness,graphrag,neutral_retrieval}_benchmark.json` | **offline_benchmark** | **Typed-tool**: 20 Q, 실제 claude routing 1.0/1.0/1.0, halluc=0 (keyword 3, FAIL). **GraphRAG @ scale** (real graph 2,895 events): 공정한 flat-retrieval baseline (6/21, refuses 6/6, 0 halluc) 대비 GraphRAG 는 21/21 — 그러나 task 가 graph-structural 이므로 graph 는 BY CONSTRUCTION 으로 높음. **Neutral text-lookup 대응** (12 Q, method-independent gold): flat_text 0.833 top1 이 graph_boosted 0.750 을 **능가** — graph 는 text 에서 lift 없음. 이 쌍이 판정을 양방향으로 한정 (query type 에 tool 을 맞출 것). **RAGAS retrieval** (real ragas 0.4.3 non-LLM: ctx-precision flat 0.833 vs graph 0.771, recall 동률) 도 동의. **RAGAS generation-side** in-session 판정 (LLM key 없음): faithfulness **1.0**, answer_relevancy **0.985** over 10 answered Q; 판정은 fixture 에 커밋, drift-guarded. 이 pass 에서 mislabel 을 잡아 수정 (llm_news_value dollar figure `measured`→`simulated`) |
| 모든 UI metrics 가 아티팩트로 해소됨 | V2-07 | Cockpit → `services/api/v2_metrics.py` → `reports/v2/**` | **offline_benchmark / measured** (per metric) | Operator cockpit 이 7 metrics 렌더링, 각각 해당 아티팩트에서 읽은 `ResultEnvelope` 로 래핑 (하드코딩 숫자 없음); rider preview + trip planner 숫자는 typed plan 유래 (faithfulness 1.0). Screenshot `docs/screenshots/v2_cockpit.png` |
| RL rebalancing (research-only) | RESEARCH | `reports/v2/research/rl_rebalancing.json` | **research** | V2-04 simulator/ledger 상의 Tabular Q-learning + PPO. Regret vs Oracle: PPO **202.9** < tabular **247.8**, 둘 다 MPC **21.6** 에 못 미침. `beats_mpc=false`; **RL advantage 주장 없음**. `ResultEnvelope` 로 모든 제품 표면에서 차단. 완료 조건 아님. `docs/v2/V2_RESEARCH_RL.md` 참조 |

V2-09 final audit (`make v2-final`, `scripts/v2_final_audit.py`) 는 이 matrix 를 커밋된
아티팩트로부터 채우고 `reports/v2/final/claim_matrix.json` 으로 미러링한다 — 세 개의
기계 검증 gate (envelope integrity, completion-artifact coverage, traceability) 와 함께. 현재
판정: **PASS — V2_COMPLETE** (31 artifacts; `reports/v2/final/v2_final_audit.md` 참조). 알고리즘
원리 + metric 정의: `docs/v2/V2_ALGORITHMS.md`.
