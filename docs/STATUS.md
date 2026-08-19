# Project Status

_Last updated: 2026-08-19_

## 정정 (2026-08-19) — structured event feed의 A1−A0 개선은 재현되지 않습니다

아래 문서 곳곳에 `A1−A0 = MEANINGFUL_POSITIVE +2.69%`로 기록된 structured-event-feed lift는
**단일 train/test 분할에서 얻은 결과이고, rolling origin에서 재현되지 않았습니다.** 새 검증
(`make v2-llm-value-rolling` → `reports/v2/llm_value/rolling_origin_ablation.json`)에서 월별 창마다
A0/A1/A2를 다시 학습해 측정한 결과는 다음과 같습니다.

| 창 | permit-active 행 | A1−A0 | A2−A1 |
|---|---|---|---|
| 2026-05 | 2,600 | **+3.96** CI [1.02, 6.68] `measured_improvement` | −3.50 CI [−5.27, −1.54] `negative_lift` |
| 2026-06 | 2,612 | **−3.46** CI [−6.10, −0.92] `negative_lift` | −1.82 CI [−2.73, −0.95] `negative_lift` |
| 2026-07 | 56 | `blocked_data` (커버리지 게이트) | `blocked_data` (news 0행) |

- **A1−A0: `sign_flips`** — 커버리지가 비슷한 두 창에서 부호가 정반대이므로 표본 부족이 아니라 실제
  불안정성입니다. **개선 주장을 철회합니다.**
- **A2−A1: `consistently_negative`** — LLM 뉴스가 도움이 되지 않는다는 부정적 결론은 측정 가능한 두 창
  모두에서 유지됩니다. 이 결론은 그대로 둡니다.
- 기존 단일 분할 artifact(`incremental_value_borough.json`)의 test 구간은 `n=2,975 / 31 day-blocks`로,
  이번 5월 창과 정확히 일치합니다. 즉 **원래 결과는 사실상 2026년 5월 한 달 평가**였습니다.
- 그 단일 분할 위에 세워진 density curve와 quality ablation의 해석도 같은 조건부입니다. 두 분석은
  "그 창 안에서의 민감도"로는 유효하지만, 베이스가 되는 +2.69% 자체가 안정적 효과가 아닙니다.
- 기존 artifact는 삭제하지 않았습니다. 재현 실패를 나란히 기록하는 편이 기록으로서 정확합니다.

아래 V2 섹션의 +2.69% 서술은 이 정정과 함께 읽어야 합니다.

## V2 kickoff — LLM net-business-value verification (scaffolding)

V2는 `claude/upgrade-v1-to-v2-fsn80p` 브랜치에 스캐폴딩되었습니다: 문서와 폴더만 존재하며, **아직 측정된
V2 결과는 없습니다**. V2 contract는 `CLAUDE_V2_APPEND_REVISED.md`(`CLAUDE.md`에서 import됨)이고, 계획은
`docs/v2/`에 있습니다(`docs/v2/README.md`부터 시작). V2는 — `reports/v2/**` 아래의 versioned artifact로 —
LLM/event feature가 측정 가능한 예측 lift를 더하는지, 그리고 그 lift가 LLM cost를 제하고도 profit으로
전환되는지를 검증합니다.

- **New docs:** `docs/v2/{README,V2_MISSION,V2_EXECUTION_PLAN,V2_CLAIMS_MATRIX,V2_EVALUATION_PROTOCOL,V2_PROFIT_REGRET_LEDGER,V2_LLM_VALUE_ABLATION,V2_MPC_DECISIONING,V2_PRICING,V2_GRAPHRAG_COPILOT,V2_KNOWN_LIMITATIONS}.md`.
- **New folders:** `contracts/v2/`, `config/v2/`, `data/fixtures/v2/`, `reports/v2/{holdout,ledger,llm_value,mpc,pricing,copilot,final}/`.
- **Phases:** V2-00…V2-09 **PASSED**. RL/QAOA은 research 전용입니다(완료 조건 아님).
- **V2-09 done (final audit):** `make v2-final` — `scripts/v2_final_audit.py`가 committed artifact를 기준으로
  포트폴리오를 판정하며, 세 개의 machine gate를 사용합니다(모든 **31**개 `reports/v2/**` artifact에 대한
  `ResultEnvelope`를 통한 envelope honesty; completion-artifact coverage; artifact_id traceability). 또한
  claim matrix를 `reports/v2/final/claim_matrix.json`으로 미러링합니다. Verdict: **PASS — V2_COMPLETE**.
  mislabeled envelope를 잡아냅니다(test). 요약은 `reports/v2/final/v2_final_audit.md`, 알고리즘 원리 +
  metric 정의는 `docs/v2/V2_ALGORITHMS.md`.
- **Research (not a gate): RL rebalancing** — `make v2-rl` (`optimization/rl/`): tabular Q-learning +
  V2-04 simulator/ledger 위에서 처음부터 구현한 numpy PPO. Regret vs Oracle: PPO **202.9** < tabular
  **247.8**, 둘 다 MPC **21.6**에 못 미침; `beats_mpc=false`, **RL advantage 주장 없음**. `mode=research`,
  `ResultEnvelope`에 의해 product surface에서 차단됨. 8 tests. `docs/v2/V2_RESEARCH_RL.md` 참조.
- **V2-08 done:** `make v2-monitor` — `ml/monitoring/run_manifest.py`가 모든 26개 `reports/v2/**`
  artifact를 인덱싱하고(run_id/claim_status/freshness/staleness → `run_manifest.json`; 0 stale),
  `ml/monitoring/delayed_labels.py`가 leakage-safe한 `pending_live_label`→`measured` loop를 실행합니다(label은
  `available_at > forecast_cutoff`인 경우에만 forecast를 마감하고, 그렇지 않으면 `leakage_rejected`). Live-traffic
  drift = `blocked_data`(live label 없음)로 정직하게 명시됨. 5 tests. `V2_MONITORING.md` 참조.
- **V2-07 done:** `services/api/v2_metrics.py` + `GET /v2/cockpit/metrics` — 모든 headline cockpit
  metric은 committed된 `reports/v2/**` artifact에서 live로 읽어 `ResultEnvelope`
  (run_id/artifact_id/mode/claim_status/freshness)로 감쌉니다. hard-coded 숫자 없음; `research` 결과는 product
  surface에서 제외; artifact 누락 시 → fake value가 아니라 blocked envelope. 4 tests가 각 값을 artifact에서
  다시 읽습니다. **UI:** cockpit `apps/web/app/cockpit/page.tsx`(claim badge + provenance)
  + rider home consumer view — 둘 다 실행 중인 앱(`make api`+`make web`)에 대해 검증되었고 headless
  Chromium으로 스크린샷됨: `docs/screenshots/{v2_cockpit,v2_rider}.png`.
- **V2-06 done:** GraphRAG typed-tool Copilot (`ml/copilot/`, `make v2-copilot`). 숫자는 오로지
  committed된 V2 artifact를 읽는 typed tool에서만 나옵니다(`artifact_id` 포함); 답할 수 없는 질문은
  거부됩니다. **20 Q에서 두 개의 router 비교** — keyword matcher vs **실제 in-session claude-opus-4-8
  routing**(no API key; `copilot_routing_claude.jsonl`). claude: routing/correctness/refusal 1.0,
  hallucinated=0(gate 통과). keyword: hallucinated=3(decoy에서 real-but-wrong-question 숫자),
  gate FAIL. **Finding:** grounding(ungrounded=0)은 둘 다 구조적이지만, wrong/answer할 수 없는 질문을
  거부하는 것에는 LLM이 필요합니다 — 그것이 여기서 LLM의 측정된 가치입니다. 8 tests. Artifact:
  `reports/v2/copilot/correctness_benchmark.json`.
  **GraphRAG half at scale** (`ml/copilot/graphrag_scale.py`): 2-event 수치는 golden-path demo fixture
  뿐이었습니다 — 실제 graph(`make seed-graph`)에는 **2,895 events / 6 zones /
  2,808 edges**가 있습니다. 21개 as-of 질문에서, FAIR한 flat-retrieval baseline(top-3 type-matched,
  zone-agnostic) 대비: flat **6/21**(grounds, 6 OOS 모두 refuse, 0 halluc — strawman 아님) vs GraphRAG
  **21/21**. **Honest caveat:** task가 graph-structural이므로(gold = graph edge) GraphRAG는 구조상
  높습니다 — 공정한 GraphRAG-vs-RAG bakeoff가 아니며; borough-tag filter라면 동점이 됩니다. 'Event→Zone
  edge가 per-zone query를 답 가능하게 만드는 것'으로 해석하십시오. Artifact + caveat:
  `reports/v2/copilot/graphrag_benchmark.json`.
  **Neutral counterpart** (`ml/copilot/neutral_retrieval.py`): 구조적 task는 graph가 질 수 없게 만들기
  때문에, mirror도 실행했습니다 — text lookup(paraphrase→event, method-independent gold를 가진 12 Q).
  `flat_text` **0.833** top1이 `graph_boosted` **0.750**을 이깁니다(graph −0.083,
  lift 없음; degree boost가 방해). 이 pair가 verdict를 양방향으로 정직하게 한정합니다: graph는
  relational/per-zone query에서 이기고, plain text는 text lookup에서 이깁니다 — query type에 tool을 맞추십시오.
  Artifact: `reports/v2/copilot/neutral_retrieval_benchmark.json`.
  **RAGAS cross-check** (`ml/copilot/ragas_retrieval.py`, real ragas 0.4.3 non-LLM retrieval metric,
  top-10): ctx-precision flat_text **0.833** vs graph_boosted **0.771** (−0.0625), recall 동점 —
  표준 tool도 graph가 retrieval lift를 주지 않는다는 데 동의합니다. RAGAS generation-side metric
  (faithfulness/answer_relevancy)은 LLM judge가 필요 → `blocked_external`(no key), 결코 fake하지 않음.
  Optional dep `pip install -e '.[ragas]'`; 없으면 ⇒ runner가 blocked_external을 기록합니다.
  Artifact: `reports/v2/copilot/ragas_retrieval_benchmark.json`.
  **RAGAS generation-side** (`ml/copilot/ragas_generation.py`): faithfulness/answer_relevancy는 LLM
  judge가 필요 → **in-session**으로 판정됨(no key; verdict는
  `data/fixtures/v2/copilot_ragas_judgments.jsonl`에 committed됨). 10개 답변된 Q: **faithfulness 1.0**,
  **answer_relevancy 0.985**. Faithfulness는 설계상 1.0입니다(답변은 tool value만 재진술); judging이 실제
  mislabel을 잡아 고쳤습니다 — `llm_news_value`가 simulated dollar figure를
  `measured`로 찍었던 것(→ `simulated`; q08은 이전에 3/4=0.75였음). Drift guard는 판정된 답변이 live Copilot과
  drift하면 run을 실패시키며; self-judgment은 caveat로 기록됩니다.
  Artifact: `reports/v2/copilot/ragas_generation_benchmark.json`.
- **V2-05 done:** bounded dynamic pricing `ml/pricing/pricing_v2_eval.py` + `pricing_v2_run.py`
  (`make v2-pricing`). Elasticity는 versioned assumption set에서, objective는 ledger, bounds/safety는
  `config/pricing_v2.py`에서 가져옵니다. 576개 seeded zone-hour: **0 guardrail violations**, safety zone은
  base-fare, credit budget 0/40 준수, **negative control**이 심어둔 out-of-bounds
  surge를 잡음; sensitivity grid(elasticity × surge-bound); **A/A switchback** effect ≈ 0 / CI가 0을 포함함
  (설계 valid). 전부 `simulated`(shadow quote, 청구된 rider 없음, causal claim 없음). 7 tests.
  Artifacts: `reports/v2/pricing/{guardrail_audit,sensitivity}.json`.
- **V2-04 done:** multi-period MPC `optimization/mpc.py` + `mpc_run.py` (`make v2-mpc`). 네 개의
  mandatory policy + Oracle를 seeded commute scenario에서, V2-02 ledger objective로 실행. Ledger cost
  (낮을수록 좋음): NoAction 1127 / Greedy 1155 / MILP 1087 / **MPC 740** / Oracle 719. **MPC가
  가장 좋은 feasible policy**(regret 21.6 vs Oracle, ~3%)이며, single-period 대비 shortage+overflow를 절반으로
  줄임; Greedy는 net-harmful(reposition > 완화된 imbalance). MPC는 forecast-only(no leakage); Oracle은 offline
  bound(regret ≥ 0); 전부 feasibility-check됨. Dollars는 `simulated`. 7 tests. Artifact:
  `reports/v2/mpc/policy_comparison.json`.
- **V2-00 done:** result envelope `contracts/v2/{enums,envelope}.py` (`ClaimStatus` 9-value +
  `ResultEnvelope`, honesty rule을 코드로 enforce, 22 tests green); `make v2-audit` gate
  (domain-drift + contract check, exit 0); audit report `reports/v2/final/v2_audit.md`.
  Findings: 0 domain drift; JC-vs-NYC data nuance 기록됨; test-count inconsistency와 legacy
  `v2-*` phase-number collision을 cleanup 대상으로 flag함.
- **V2-01 done (measured):** `ml/forecasting/h3_multiholdout.py` (`make v2-holdout`) +
  `promoted.py` serving loader. 실제 JC Citi Bike Mar–Aug 2024, **210,042**개 H3 zone×hour row /
  **234** zone, 3개 rolling monthly window. Promoted `hist_gradient_boosting`; aggregate
  **WAPE 0.4828 ± 0.0030, MASE 0.7996**(모든 window에서 B0 seasonal-naive ~0.648을 이김).
  Artifacts: `reports/v2/holdout/{h3_multiholdout,promoted_model}.json`. 5 leakage/window tests.
  Scope: JC slice, B1 feature만(events = V2-03), promotion pool bounded, API wiring = V2-07.
- **V2-02 done:** profit/regret ledger `optimization/ledger.py` + `ledger_run.py` (`make v2-ledger`)
  + typed `contracts/v2/ledger.py` + versioned `config/v2/assumptions.yaml`. 114,079개 zone-hour
  decision에 걸쳐 V2-01 forecast는 seasonal-naive 대비 **+$103,271**을 net함(부호는 9개 cost
  setting 전체에서 robust), regret vs Oracle는 **$218,697**. Unit count는 measured; dollars는 `simulated`(assumption
  아직 sourcing 안 됨). 8 tests(no-double-count, Oracle upper-bound). Relocation은 V2-04로 연기됨.
  Artifact: `reports/v2/ledger/profit_regret.json`.
- **V2-03 done (honest null):** `ml/forecasting/llm_value.py` (`make v2-llm-value`) — 3개 arm
  (No-Event/Rule-Event/LLM-Event = B1/B2/B4), 공유 promoted model + split, block-bootstrap CI,
  ledger profit, LLM cost model. 실제 JC 2026 H1 + 실제 GDELT NYC 2026 news(371 articles). Arm들이
  **동일**(ΔWAPE=0, CI[0,0]), event coverage 0.3% → verdict **`insufficient_event_overlap`**
  (`blocked_data`); LLM actual $0(mock)/est real $0.0061, **net LLM value −$0.01**. v1의 gap을 엄밀하게
  확인함; framework(arms/CI/cost)는 마련됨. 6 tests. Artifact:
  `reports/v2/llm_value/incremental_value.json`. Unblock path는 report에 문서화됨.
  **Borough re-measurement — FAIR test** (`make v2-llm-value-borough`, 19.9M 실제 NYC trip,
  borough×hour, 5-mo train Jan–Apr, test May with 216 news row, citywide attribution 4→35):
  **A1−A0 (permitted, structured) = measured_improvement** (WAPE 0.1069→0.1047, CI [1.87,5.88],
  +$33k — v1을 robust하게 재현); **A2−A1 (LLM-news) = negative_lift** (WAPE 0.1047→0.1075,
  CI [−6.02,−3.71], **net LLM value −$23,730**). **V2 answer (this data): structured event feed
  는 돈이 되고, LLM-from-news는 net-negative** — 공정한 test에서조차. Caveat: borough event
  effect는 작고(~0.002 WAPE) sample-sensitive. Artifact: `incremental_value_borough.json`.
  **Real-LLM extraction (decisive):** sandbox에 API key가 없으므로, claude-opus-4-8(this session)이
  23개의 clean NYC event를 hand-extract함(`data/fixtures/news_live/claude_events_2026h1.jsonl`,
  `--claude-events` path). test May, 336 clean news row로 re-run: A1−A0 measured_improvement
  (0.0908→0.0883); **A2−A1은 여전히 negative_lift** (0.0883→0.0905, CI [−5.32,−1.56], net LLM value
  −$17,789). LLM-from-news는 **실제 high-quality extraction으로도** net-negative입니다(news가
  structured feed 대비 sparse/coarse/redundant) — mock artifact가 아님. 6 tests.
- **V2-03 LLM Feature Value metric** (`ml/forecasting/llm_feature_value.py`): "LLM feature가 정확도를
  의미 있게 개선했는가?"를 하나의 decision으로 정식화함. Score = **LLM-active subset**에서의 상대 WAPE
  reduction(전역적으로 희석하지 않음) + day-block bootstrap CI; `MEANINGFUL_*`는 |skill|≥1% AND CI가 0을
  제외할 때만, 그 외에는 `NO_MEANINGFUL_EFFECT`/`INSUFFICIENT_SUPPORT`(fake verdict 없음).
  Measured (test May, Jan–Apr train 10,655 row, 336 active): **`MEANINGFUL_NEGATIVE`, active skill
  −5.52%, CI [−17.51,−0.98]** → LLM feature는 발화하는 곳에서 정확도를 측정 가능하게 저하시킵니다. artifact에
  `llm_feature_value_metric`으로 emit되며; 6개 synthetic unit test를 가진 pure fn
  (`tests/unit/test_llm_feature_value.py`).
- **V2-03 feature improvement + graph contribution** (`ml/forecasting/event_features_v2.py` +
  `llm_graph_value.py`): feature engineering을 수정함(event-time anchor + half-life decay +
  type-scoped borough, flat-24h-from-publish box를 대체) 그리고 graph neighbor-spillover
  arm을 추가함. 실제 NYC demand로 measured (test May): **improved feature A2−A1 = `NO_MEANINGFUL_EFFECT`
  −0.4%** (CI [−4.90,1.36]) — harm이 **제거됨**(−5.52%였음), 이제 positive가 아니라 neutral.
  **Graph A3−A2 = `NO_MEANINGFUL_EFFECT` −1.32%** (CI [−3.76,0.72]) — borough grain에서 graph는
  **not proven**(coarse zone 5개뿐; structured feed가 이미 dense). graph claim의 공정한 venue는
  H3-zone grain(기존 `pipelines/features/graph_features.py`)이며, 아직 실행되지 않음. Honest null, fake 아님.
  6 pure-builder unit test. Artifact: `reports/v2/llm_value/graph_contribution.json`.
- **V2-03 "news→permit-DB" reconstruction** (`ml/forecasting/llm_permitize_value.py`, hypothesis
  REFUTED): news를 permit-schema record로 재구성하면(정확한 event_start/end +
  구체 borough, `claude_events_permitized_2026h1.jsonl`) 가치를 회복하는지 test함. **해로웠습니다**:
  permitized−A1 = **`MEANINGFUL_NEGATIVE` −6.31%** (CI [−25.2,−5.5]), raw news보다도 나쁨
  (WAPE 0.0940 vs 0.0883). **Structure가 빠진 재료가 아닙니다** — permit feed가 통하는 것은
  event DENSITY 때문(63,070 events → learnable coefficient); news는 ~19개를 주고, 그 sparse event를
  sharp/confident하게 만드는 것은 confident noise를 주입합니다(strike는 bike demand를 올릴 수도 내릴 수도
  있음; 그렇게 적은 수로는 unlearnable). 4개 event가 leakage-drop됨(retrospective review가 event를 post-date).
  Honest negative, fake 아님. 8 pure-builder test. Artifact: `permitize_contribution.json`.
- **V2-03 (a) news-as-importance-weight** (`ml/forecasting/llm_importance_weight_value.py`): dense
  permit feed는 유지하고, news는 그것을 modulate만 하게 함 — `ev_active×(1+news_salience)`, news 없는 곳은
  unchanged. **역시 negative: `MEANINGFUL_NEGATIVE` −7.82%** (CI [−25.6,−5.9], WAPE 0.0883→0.0925). 예시
  row가 이유를 보여줍니다: Winter Storm Fern이 permit을 63→119.7로 증폭하지만, blizzard는 bike demand를
  *억제*합니다 → wrong-signed. Artifact: `importance_weight_contribution.json`.
- **V2-03 (b) H3-grain graph test = `blocked_data`**: fine H3 graph는 geocoded event가 필요하지만; 실제
  permit/news event는 borough-tag만 되어 있음(no coordinate). fabricate 아님; borough-grain graph
  null이 가장 미세한 fair test로 유지됩니다.
- **V2-03 (signed LLM demand signal)** (`ml/forecasting/llm_signed_value.py`): LLM이 signed
  `demand_effect∈[−1,+1]`를 emit함(blizzard −0.9, festival +0.5, LIRR shutdown +0.6 via substitution) →
  `news_demand_signal = demand_effect×severity×decay`. **LLM sign-correctness 0.77**(방향은
  맞음), harm 제거됨(−7.82%→−2.04%), 하지만 여전히 **`NO_MEANINGFUL_EFFECT`** (CI [−7.26,+1.44], WAPE
  0.0883→0.0906). 이유: autoregressive lag(dep_lag_1/24/168, roll_mean_24)이 진행 중인 event의
  demand를 이미 encode함 → news signal은 **redundant**. 3개 unit test 추가.
- **V2-03 (post-processing correction)** (`ml/forecasting/llm_postprocess_value.py`): news를
  output correction `pred+Σα_ch·signal_ch`로 적용하며, per-mechanism(n-dim) factor를 train
  residual에 calibrate하여 test에 적용. **`MEANINGFUL_NEGATIVE` −21.36%** (WAPE 0.0883→0.0899). Fitted factor는
  absurd/wrong-signed(α[gather]=−470, α[transit]=−478) → sparse calibration이 **overfit**하여 test에서
  실패. sparsity 문제가 model에서 post-processing step으로 옮겨졌을 뿐입니다.
- **V2-03 (horizon sweep)** (`ml/forecasting/llm_horizon_value.py`): operational lead time에서 event
  value가 커지는지(recent lag 제거) test함. 그렇지 **않습니다** — permit A1−A0는 MEANINGFUL_POSITIVE
  **+2.69%**로 nowcast(h=1)에서만; h≥6에서는 baseline WAPE가 두 배가 되며 neutral(0.09→0.18→0.22, noisier).
  News는 모든 horizon에서 neutral-to-negative. null은 nowcasting artifact가 아닙니다.
- **V2-03 root-cause (density curve + quality ablation)** (`ml/forecasting/llm_density_curve.py`,
  `llm_quality_ablation.py`): "그저 sparsity 때문인가?"를 엄밀히 답합니다. **Density curve**(dense permit을
  subsample, precision+timing 고정): news-scale(≤100 events; news~19)에서 dead, N=300에서 +2.03%,
  이후 non-monotonic → density는 necessary but not sufficient. **Quality ablation**(density FULL,
  한 axis만 degrade): coarse-time −0.33%, citywide +0.53%, retro +1.01% — **각각이** full
  +2.69%를 **붕괴**시킴. 입증된 원인 = **dense + precise-time + precise-location + forward-looking**의
  conjunction; news는 네 가지 모두 실패; news를 더 모으면 density만 고칠 뿐 structural axis는 못 고칩니다.
- **V2-03 news condition audit** (`ml/forecasting/news_condition_audit.py`): news event 중 2/23만
  forward-looking, 1/23만 forward+precise 둘 다(June, test 밖) → permit feed의 조건을 만족하는
  subset은 ~empty; 4-D encoding은 source에 없는 정보를 더할 수 없습니다(news는 본질적으로 coincident/
  retrospective).
- **V2-03 synthetic ceiling** (`ml/forecasting/llm_synthetic_ceiling.py`, **claim_status: simulated**):
  forward-looking precise dense event shock를 실제 demand에 disclosed injection → LLM
  post-correction **+10.43% MEANINGFUL_POSITIVE**(feature +20.86%); news-scale density에서는 INSUFFICIENT.
  post-correction/method가 좋은 event를 활용할 수 있음을 입증 — real-news null은 SOURCE 문제이지
  method limitation이 아닙니다. real-news claim이 아님; injected effect는 완전히 disclose됨.
- **V2-03 overall (negative result, fully understood — but NOT a dead project):** 일곱 번의 시도
  (extraction/graph/permit-reconstruction/importance/signed/post-processing/horizon)가 모두
  LLM-from-news demand value에 대해 neutral-to-negative; root cause = sparsity + sign heterogeneity
  (handled, 77% right) + lag와의 redundancy. **그러나 프로젝트의 measured positive는 유효합니다:**
  structured event layer가 forecast를 개선하고(A1−A0 **+2.69%**, **+$33k** ledger — core thesis),
  LLM은 routing/grounding에서 measured value를 가집니다(V2-06 Copilot 1.0 vs keyword 0.75, halluc 3→0).
  정직한 V2 verdict: LLM의 검증된 가치는 **structuring/routing/explanation + event layer를 구동하는 것**에
  있지, sparse retrospective news에서 demand accuracy를 짜내는 데 있지 않습니다. Pipeline은
  event-source-agnostic입니다(dense forward-looking geocoded LLM stream이라면 동일한 A1 slot에 들어감;
  GDELT news는 그런 stream이 아님).
- **Honesty:** 모든 V2 result cell은 `pending`; v1 숫자는 어떤 것도 V2 claim에 복사되지 않았습니다. 아래의 v1
  결과는 V2 phase가 재측정하기 전까지 현재의 measured record로 유지됩니다.

## Measured results — event-aware forecasting lift (real data)

핵심 product claim을 실제 데이터로 end-to-end 테스트했습니다(`docs/EVENT_LIFT_FINDINGS.md` 참조):
Jan–May 2026로 train하고 June을 hold out하여, demand+calendar baseline을 동일 model에
event-derived feature를 준 것과 비교합니다.

- **NYC permitted events → measured improvement.** 20.3M개 실제 Citi Bike trip을
  borough×hour로 stream하고, 63,070개 실제 NYC permitted event(leakage-safe, public permit schedule)와
  join함. June-holdout WAPE가 **0.1013 → 0.0996 (−1.65% relative)**로 하락; paired day-block bootstrap verdict
  **`measured_improvement`**, 95% CI **[0.36, 5.11]**(above zero). 재현:
  `python -m ml.forecasting.borough_event_lift`. Model-attributed, causal 아님; borough grain은
  H3 product grain의 문서화된 approximation입니다.
- **June weather → honest negative.** NOAA Central Park weather로 동일 설계: WAPE **0.4868 →
  0.4893**, verdict **`negative_lift`**(CI가 0 아래). 온화한 June은 weather variance가 적음; 결과는
  숨기지 않고 있는 그대로 보고됨. 재현: `python -m ml.forecasting.weather_lift`.

## LLM extraction providers (opt-in)

event extractor는 `LLM_PROVIDER`(`config/settings.py`)로 provider를 선택합니다. Demo Mode와 모든
test는 deterministic offline `mock`을 사용합니다. 이제 두 개의 real, opt-in provider가 동일한
`LlmProvider.extract(article) -> list[dict]` interface 뒤에 존재하며, 각각 lazy import되어 mock path는
SDK/key가 필요 없습니다:

- **`anthropic`** (Claude) — `ANTHROPIC_API_KEY` / `LLM_MODEL`.
- **`openai`** (GPT-4o) — `OPENAI_API_KEY` / `OPENAI_MODEL` (default `gpt-4o`); `pip install -e ".[llm]"`.

둘 다 §8/§22 guardrail을 동일하게 enforce합니다: forced structured output, verbatim evidence
grounding, deterministic gazetteer geocoding(never model coordinate), bounded severity/confidence,
모든 extraction의 provenance, 그리고 honest degrade(SDK/key가 없으면 raise — 절대 fabricated event 아님).
`tests/unit/test_openai_provider.py`와 `test_anthropic_provider.py`로 커버됨.

## GraphRAG operator copilot (V2-08)

operator "운영 도우미"(`POST /v2/operator/ask`, `/statistics`에 표시)가 이제 LLM key가 설정되면
자동으로 upgrade됩니다. `LLM_PROVIDER=openai`/`anthropic` + key가 있으면 **GraphRAG**로 답합니다:
`services/api/graphrag.py`가 as-of event graph를 retrieve하고(event + grounded evidence +
affected zone + model-attributed forecast delta — dashboard가 쓰는 것과 동일한 ReplayEngine artifact)
model에게 *오직 그 context만 사용하고 event id를 citing하여* 답하도록 요청합니다. Cited id는 context에 대해
검증되므로, copilot은 graph에 없던 event를 결코 노출할 수 없습니다(§22). 기본 `mock` provider에서는 —
또는 SDK/key 누락, 또는 임의의 provider error에서는 — deterministic rule-based `ops_ask`로 degrade합니다.
response는 `answer_mode`(`graphrag_llm`/`rule_based`) + validated `citations`를 얻습니다; UI는 badge와
cited event를 보여줍니다. `services/api/llm_chat.py`는 degrading chat helper입니다(test-injectable, offline).
`tests/integration/test_graphrag_copilot.py`로 커버됨. local key setup은 `docs/LOCAL_GPT.md` 참조.

## Event graph built from real repo data

`make seed-graph`(`scripts/build_graph.py`)는 §9 event graph를 이미 repo에 있는 데이터로부터 직접
채우므로, 더 이상 2-event demo가 아닙니다. **news**(`data/fixtures/news_live/*.jsonl`
→ mock extraction, provenance-rich)와 **NYC permitted event**
(`nyc_permitted_events_filtered.jsonl.gz`, 63k row → borough-centroid grounded, spatially rich)를 결합합니다.
Measured build(`--permitted-limit 2000`): **2,090 events / 5,770 nodes / 11,850 edges / 6 zones**,
replay-idempotent, audit clean; portable node-link JSON snapshot이 `data/processed/graph/` 아래에
기록됨(git-ignored). `--backend neo4j`는 live server에 씁니다. graph는 audit/provenance surface(§9)로
유지되며; forecasting feature는 이 critical path 밖의 pure function으로 남습니다.

## Current status — V2 usability update (UI, search, operator analytics)

V1 위에 얹은 backward-compatible, usability 중심의 increment. Scope: consumer bike-share 앱 스타일로
재설계된 rider home, station **search**, 더 강한 **operator statistics /
analytics** 화면. 어떤 forecasting/pricing/experiment claim도 바뀌지 않습니다 — 모든 것이 offline이며
`demo-heuristic-v1` demo heuristic으로 정직하게 label됩니다(measured Phase 06 model이 아님).

- **Rider home redesign** (`apps/web/app/page.tsx`) — 눈에 띄는 search bar, availability summary +
  filter chip(전체 / 빌리기 좋아요 / 곧 부족), 깔끔한 station list, 그리고 event-aware demand shift와
  "why busy" trace link가 있는 tap-to-open station detail sheet.
- **Station search** — 새 offline endpoint `GET /v2/rider/stations/search`(Korean / English /
  alias / typo-tolerant substring match over `data/fixtures/station_gazetteer.json`)로, 각 hit를
  operational fixture의 as-of live inventory로 hydrate합니다(query text에서 절대 추론하지 않음).
  Empty query는 availability로 순위 매긴 모든 station을 반환합니다.
- **Operator statistics** — 새 endpoint `GET /v2/operator/statistics`(실제 aggregation: system
  utilization, availability distribution, shortage load, type/effect별 event mix, demand-delta
  spread, per-zone breakdown)를 새 `/statistics` 화면에 stacked availability
  bar, event-type / top-surge bar list, per-zone table로 렌더링합니다. 모든 값이 v1
  endpoint와 reconcile되고 as-of leakage boundary를 존중합니다.
- **Event-window timeline** — 새 endpoint `GET /v2/operator/timeline`이 replay window(12:00→18:00)에
  걸쳐 각 hour에서 as-of aggregate(shortage, Δ, event count)를 event-onset marker와 함께 재계산하여
  `/statistics`에 두 개의 inline-SVG area+line chart로 렌더링합니다. leakage boundary를 시각적으로 보여주고
  (onset 전까지 flat), `event_count`는 monotonic non-decreasing입니다.
- **Optimal extra-bike allocation** — 새 endpoint `POST /v2/operator/rebalancing/allocate`와
  `optimization/classical/allocation.py`: operator가 **M**개의 extra bike를 입력하면 allocator가
  asymmetric objective(shortage 3 : overflow 1) 하에서 benefit을 최대화하도록 분배하며,
  dock capacity와 `Σ added ≤ M`을 존중합니다. Objective는 separable/convex이므로 greedy가 globally
  optimal입니다(brute-force enumeration에 대해 검증됨). 유익한 배치가 없는 surplus bike는 강제 배치되지 않고
  정직하게 held back됩니다. `/rebalancing`에 M input이 있는 "추가 자전거 최적 분배" planner로 렌더링됨.
- New code: `services/api/v2.py`, `data/fixtures/station_gazetteer.json`,
  `apps/web/app/statistics/page.tsx`; endpoint는 `services/api/app.py`에 wiring됨; typed client는
  `apps/web/lib/api.ts`.
- Tests: `tests/integration/test_api_v2.py`의 **18 new** integration test + `tests/unit/test_allocation.py`의
  **7** unit test(search matching, live hydration, as-of boundary, statistics
  consistency, timeline onset/monotonicity, brute force 대비 allocation optimality, honest hold-back)
  — 전부 pass. 전체 non-torch suite: **204 passed, 1 skipped**; web `tsc` clean, `next build` green
  (12 routes), 새 module에 ruff + mypy clean. 9개의 `torch`-dependent recsys/model test는
  여기서 실행할 수 없습니다(PyTorch wheel index가 container proxy에 의해 차단됨) — 이 변경과
  무관합니다.
- **Rider / operator experience split** — top-level role switch(🚲 라이더 / 🛠 운영자, persisted).
  Rider mode는 깔끔한 consumer view(operator tool 숨김, read-only replay clock); operator mode는
  전체 tool tab bar + replay control을 보여줍니다. Operator route로의 deep-link는 operator
  mode를 auto-select합니다. 추가로 Korean 가독성을 위한 **Noto Sans KR** gothic font(`next/font`로 self-hosted).
- **Rider map view** — rider home의 ☰ 목록 / 🗺 지도 toggle; map은 station을 실제 lat/lng로
  project하는 self-contained SVG(offline, tile provider / API key 없음)로, availability로 marker를 색칠하고
  🔥 surge ring을 붙이며, 클릭 시 station detail sheet를 엽니다.
- **Rider copilot** — rider home의 no-LLM natural-language ask(`POST /v2/rider/ask`).
  deterministic parser(`services/api/rider_copilot.py`)가 Korean/English query를
  allowlisted intent로 분류하고 **오직 live tool result에서만** 답합니다(숫자는 verbatim으로 복사, 조작 없음);
  unsupported query는 지어낸 답이 아니라 clarification을 반환합니다.
- **Dynamic fare simulator** (V2-05) — bounded scarcity surcharge(1.00/1.10/1.25/1.50) +
  balancing credit로서, **SIMULATED SHADOW** quote(rider에게 절대 적용되지 않음). Pure kernel
  (`ml/pricing/dynamic.py`)이며 guardrail을 in-kernel로 enforce: safety/emergency event → base,
  stale data → base, hard 1.50 cap, `base + surcharge == final`(auditable), 그리고 **rider
  identity / reduced-fare / protected attribute를 절대 사용하지 않음**. What-if scenario toggle이 있는
  operator `/pricing` 화면. `POST /v2/pricing/quote`.
- **Dynamic-fare revenue comparison** (V2-05) — `make v2-evaluate-revenue`
  (`ml/pricing/revenue_eval.py`)가 flat vs event-aware dynamic을 **실제 shipped된
  `/v2/pricing/quote` path**(post-event cutoff as-of replay engine)로 pricing하고 **명시적
  demand-elasticity** model로 revenue layer를 추가합니다. Measured (SIMULATED SHADOW): elasticity 0.5에서, event-aware
  dynamic은 **+0.4% network revenue with zero lost rentals**(surcharge는 supply-constrained event zone에서만
  발화하여, 어차피 매진되는 bike에서 value를 포착). **Elasticity sweep**(0→1.5)은 uplift가 robust함을 보이고,
  **event-severity what-if**(×1/×2/×3)은 event intensity에 따라 revenue가 상승함을 보입니다(uplift +0.4%→+1.0%→+1.5%,
  surcharge tier 1.10×→1.25×). flat pricing은 그 value를 놓칩니다. Report: `reports/v2/pricing/revenue_sim.json`(+`.md`).
- **Ops copilot** (V2-07) — operator NL assistant(`POST /v2/operator/ask`). deterministic
  parser가 query를 allowlisted intent로 매핑하고 **오직 dashboard artifact에서만** 답합니다
  (`operator_statistics` / `pricing_quotes`) — 임의의 SQL 없음, fabricated 숫자 없음; fact는
  statistics endpoint와 일치하도록 assert됨. 답변은 매칭되는 화면으로의 **deep-link**를 반환할 수 있습니다.
  `/statistics`에 card로 렌더링됨.
- **Hybrid geo-semantic search** (V2-03) — provider-based(`GET /v2/rider/search/hybrid`): BM25 +
  char-n-gram vector + geo를 RRF로 fuse; hit는 operational store에서 re-hydrate됨. Offline
  `LocalHybridProvider`가 tested path; optional `ElasticsearchProvider`는 사용 불가 시 local로 degrade.
  `make v2-evaluate-search`가 Recall@10 / MRR / NDCG@5 / geo-valid를 report함(gold set에서 전부 1.0).
- **Predictive lift protocol** (V2-02) — pure, tested machinery(chronological split + purge/embargo,
  event-block bootstrap CI, honest verdict rule). Demo run(`GET /v2/model/predictive-lift`,
  `make v2-evaluate-predictive-lift`)은 실제 coverage를 측정하여 정직하게 **`blocked_data`**를 보고함
  (demo fixture가 gate보다 훨씬 아래); measured claim에는 실제 news backfill + training이 필요합니다.
  Model Lift Lab에 노출됨.
- **Real Citi Bike network (45 stations)** — operational fixture는 이제 GBFS
  `station_information`/`station_status`에서 import한 **40개 실제 Citi Bike station**과, golden-path event
  demo가 여전히 shock를 구동하도록 유지된 **5개 Jersey City / Hoboken event-zone station**(역시 실제)을
  담습니다. 모든 것(search, map, stats, pricing, allocation, copilot)이 이 network에서 실행됨; label된
  pricing/switchback *simulation*은 imported live network와 무관하게 deterministic하도록 5개 event-zone
  station으로 decouple됨.
- **Real station import (GBFS)** — `make v2-import-stations` / `POST /v2/operator/stations/import`가
  GBFS `station_information`(free, no key)에서 **실제 Citi Bike network**를 fixture로 pull합니다.
  `--from-file` / `--status-file`은 host에 egress가 없을 때 로컬 다운로드된 feed를 import합니다;
  gracefully degrade. operator statistics 화면에 preview 버튼.
- **On-demand live news sync** — "뉴스 동기화" 버튼(`POST /v2/news/sync`)이
  **GDELT DOC 2.0**(free, no key)에서 실제 news를 pull하여 vector store에 accumulate합니다. 실제로
  fetch했을 때만 `live`로 label됨; network failure는 reason과 함께 `degraded`를 반환하며 **fabricated
  article 없음**(offline sandbox → degraded; egress가 있는 deploy → live).
- 전체 spec과 reproduction step은 `docs/V2_UX_UPDATE.md` 참조.

---

## Previous status — V1 complete (with honest data blocks)

**v0 (Phases 00–09) complete**, 그리고 그 위에 backward-compatible increment로 **V1 (V1-00 … V1-09) 구현됨**.
per-phase 세부는 `docs/V1_EXECUTION_LOG.md`, final audit는 `reports/v1/V1_FINAL_AUDIT.md` 참조.

- Done: V1-00 contracts · V1-01 news backfill (+ **real GDELT** opt-in) · V1-02 incremental features
  (== full rebuild) · V1-03 model registry(measured B0-B4) · V1-04 event-lift gate · V1-05
  live-shadow(pending labels) · V1-06 anomaly detection · V1-07A–D recommendation + pricing
  (measured retriever / simulated policy) · V1-08 clustered-switchback experiments(simulated) ·
  V1-09 UI(8 screens) + offline golden-path E2E + audit + packaging. 추가로 **FAISS news vector
  store**(accumulating news, semantic search, same-event clustering).
- Honest blocks: **event lift** = `insufficient_event_overlap`(claim disabled); **real-news
  coverage** = `BLOCKED_DATA`(실제 backfill이 gate를 통과할 때까지); **recommendation / pricing /
  experiments** = `simulated`; **live-shadow** prediction = `pending`.
- Tests: **199 passed, 1 skipped**(`make test`); web `tsc` clean; ruff clean; offline E2E green.
- Commands verified: 아래의 `make` target 참조(각각 실제, tested workflow를 실행).

---

## v0 milestone detail (Phases 00–09)

**Phase 08 — Rebalancing & Quantum Research Mode: complete.** (Phases 00–07도 complete.)

### Phase 08 — Rebalancing & Quantum Research Mode (complete)

`optimization/classical/`와 `optimization/quantum/`(§14) 및 API/UI wiring 구현:

- **Classical** (`problem.py`, `objective.py`, `feasibility.py`, `greedy.py`, `enumeration.py`,
  `milp.py`, `config/rebalancing.py`) — post-plan inventory에 대한 asymmetric operational objective
  (shortage > overflow, 3:1); explicit feasibility check(outflow ≤ bikes, final ≤ capacity,
  non-negative integer move, vehicle-capacity limit)로 infeasibility를 plain text로 report;
  greedy baseline(always feasible), `scipy.optimize.milp`를 통한 exact **MILP**, enumeration
  oracle. Verified: **MILP cost == enumeration cost**(optimal) 및 ≤ greedy; binding vehicle
  capacity 존중됨.
- **Quantum Research Mode** (`qubo.py`, `qaoa.py`) — small instance → QUBO with 문서화된
  bounded-binary variable mapping과 quadratic imbalance surrogate energy. **QUBO brute-force
  optimum == exact enumeration optimum**(required, §14.2), encoding이 모든 bit vector에 대해 surrogate와
  일치하고, crafted instance에서 QUBO plan이 MILP plan과 일치함. QAOA는
  optional(lazy `qiskit`); 여기에는 qiskit이 없으므로 그 test는 문서화된 reason과 함께 skip됨.
  Research only; simulator ≠ hardware; advantage claim 없음.
- **API/UI** — `POST /v1/rebalancing/solve`가 이제 typed, feasibility-checked plan을 반환함
  (`services/api/rebalancing.py`, `schemas.py`, `app.py`); 501은 사라짐. Target은
  cutoff as-of `demo-heuristic-v1` forecast delta에 의해 event-exposed zone에서 상향됨(labelled demo
  heuristic, measured model 아님). `apps/web/app/rebalancing/page.tsx`가 plan을 렌더링함.
  `make rebalance-demo`가 전체를 offline으로 실행함.

### Phase 07 — FastAPI & Next.js UI (complete)

- **API** (`services/api/`) — offline FastAPI replay service: `/v1/health`, `/v1/replay/state`,
  `/v1/replay/set-cutoff`, `/v1/events`, `/v1/forecasts`, `/v1/zones/{id}/explanation`,
  `/v1/scenarios`, `/v1/rebalancing/solve`. 모든 response는 mode/cutoff와 model/feature
  version을 담음; explanation은 evidence-backed; demo forecaster는 label된
  `demo-heuristic-v1`(Historical Replay)로, measured Phase 06 model과 구분됨.
- **UI** (`apps/web/`) — Next.js App Router, TS strict: Control Tower, Why Changed, Scenario Lab,
  Rebalancing Planner. API를 consume; Historical Replay vs Live 시각적으로 구분됨.

### Phase 06 — Forecasting, Tuning & Evaluation (complete)

`ml/forecasting/`(§11) 구현: seasonal-naive baseline, six-algorithm model zoo,
rolling-origin temporal CV, GridSearch tuning, permutation-importance feature selection,
B0–B4 ablation, 그리고 §11.4 metric — 실제 June-2026 데이터로 실행.

- **No leakage in evaluation** (`splits.py`) — 최근 72h는 untouched out-of-sample
  test; GridSearch는 이전 span에서 3개의 expanding-window fold로 cross-validate; imputation과
  scaling은 fold별로 fit됨. Random K-fold는 절대 사용되지 않음(§11.3).
- **Model zoo + GridSearch** (`models.py`, `config/forecasting.py`) — ridge, knn, random_forest,
  extra_trees, gradient_boosting, hist_gradient_boosting, 각각 tuned grid 포함; seed 42.
- **Metrics** (`metrics.py`) — WAPE(zero-denominator 정의됨), MAE, MASE(explicit seasonal
  scale), event-window WAPE, peak-direction accuracy, forecast-delta stability.
- **Feature selection** (`feature_selection.py`) — test holdout에 대한 permutation importance;
  top-12 reduced model이 full 32-feature model과 일치함.
- **Honest event ablation** — runner가 as-of event/graph feature가 June window에서 0임을 검증
  (assume가 아님)함(curated event가 데이터를 post-date, §5.2), 따라서 B2–B4가 B1을 재현함.
  plainly report됨(§11.4, §22); interpretation과 figure는 `README.md` / `docs/`.

### Phase 05 — As-of Graph Feature Builder (complete)

`pipelines/features/graph_features.py` + `kernels.py`(§10, §5.2) 구현:

- **Pure kernels** (`kernels.py`) — `haversine_km`, `exp_distance_decay`, `half_life_weight`;
  side-effect free하고 unit-test됨(§10 "mathematical kernel as pure functions").
- **Builder** (`build_graph_features`) — `forecast_cutoff`에 대해, `available_at <= cutoff`인
  event만 사용하여 per-zone `FeatureSnapshot`을 emit함(§5.2). §10
  feature set을 생성함: `event_count_{6,24}h_by_type`, `source_weighted_severity`, `unique_source_count`,
  `duplicate_article_ratio`, `confidence_mean/max`, `distance_decayed_impact`,
  `time_to/since_event_start`, `event_remaining_duration`, `neighbor_zone_impact`,
  `capacity_shock_exposure`, `transit_disruption_exposure`. `source_event_ids`를 보존함.
- **Config-reproducible** (`config/graph_features.py`, `GraphFeatureConfig`) — half-life,
  radius, decay scale, hops, source weights, confidence floor, feature version. 동일 event +
  동일 cutoff + 동일 config → identical output.

### Phase 04 — Neo4j Graph Upsert (complete)

`pipelines/graph/` 구현 — backend-neutral event graph(§9):

- **Model** (`model.py`) — `build_graph_ops`가 event + 해당 source article을 §9
  node/relationship set으로 변환함: Article, Event, EventType, Place, H3Zone, Source(Station reserved),
  `Event -> Place -> H3Zone`를 통해 `Event -[:AFFECTS]-> H3Zone`를 wiring하여 graph가 numeric
  feature를 feed하게 함(그러지 못하는 graph는 금지된 decoration, §9). 작은 place gazetteer
  (`config/places.py`)로 mock extractor가 event에 grounded location을 붙일 수 있음.
- **Stores** (`store.py`, `neo4j_store.py`) — `GraphStore` interface with **offline
  in-memory** backend(idempotent MERGE semantics; Demo/test는 DB 불필요)와 optional
  **Neo4j** backend(parameterized, idempotent Cypher 사용, lazy driver import, `.[graph]` extra).
- **Cypher** (`cypher.py`) — pure, unit-tested builder: label별 하나의 uniqueness constraint
  (`IF NOT EXISTS`), MERGE-on-key node upsert, MERGE relationship upsert. Label/rel-type은
  고정된 allowlist에서 옴; value interpolation 없음.
- **Audit** — orphan node와 provenance가 없는 event를 flag함(demo graph에서 둘 다 0).

### Phase 03 — LLM Event Extraction (complete)

`pipelines/events/`를 provider interface와 deterministic mock(§8)으로 구현:

- **Provider** (`provider.py`) — `LlmProvider` ABC + `MockLlmProvider`: keyword-ontology
  extractor, network/key 없음. 동일 fixture + prompt version → identical output; stable event id.
  Evidence span은 article의 exact substring(grounded); per-type demand/capacity effect는
  directional only(예: transit disruption → bike demand *increase*), severity는 bounded prior.
- **Extractor** (`extractor.py`) — **bounded retry** 하에서 Pydantic으로 candidate를 검증하고,
  evidence grounding을 verify하고, configurable confidence
  threshold에서 accept/quarantine/reject를 설정하고, near-identical event를 **deduplicate**함
  (token-Jaccard, provenance merging). Rejected/quarantined event는 유지됨(auditable); 실패 시 final validation error가 기록됨.
- Config (`config/events.py`): keyword ontology, effect prior, threshold, dedup — 전부 tunable.

### Phase 02 — Demand Aggregation & Feature Store (complete)

`pipelines/features/`에 demand feature pipeline 구현:

- **Temporal kernels** (`temporal.py`) — naive wall-clock time을 **explicit DST handling**과 함께
  `America/New_York`로 localize하는 pure function: spring-forward(nonexistent) time은
  gap을 가로질러 shift, fall-back(ambiguous) time은 earlier occurrence로 resolve — 절대
  silently drop 안 함(§5.3). 추가로 local-hour flooring과 correct한 23/25-hour DST day를 산출하는
  gap-free hourly index. Citi Bike collector도 이제 이 localization을 사용함.
- **Zone assignment** (`zones.py`) — coordinate별 H3 res-9 cell(§4), `h3`에 대한 thin wrapper.
- **Aggregation** (`aggregate.py`) — trip → primary grain(H3 zone × local
  hour)의 `DemandCell`: start의 departure, end의 arrival, `net_flow = arrivals - departures`. 새 contract
  `DemandCell`(§4, §6).
- **Leakage-safe features** (`lags.py`) — per-zone dense hourly reindex(missing hour = 0),
  lag feature(1h/24h/168h)와 shifted rolling mean(3h/24h). hour t의 모든 feature는
  strictly hours < t를 사용함; current target은 절대 자신의 feature에 들어가지 않음; zone 간 wrap 없음(§5.4).
- **Calendar features** (`calendar.py`) — ablation B1의 "calendar" layer를 완성함(§11.2):
  hour-of-day, day-of-week, weekend, morning/evening rush, US federal holiday, 그리고 hour와 weekday의
  cyclical(sin/cos) encoding. 이것들은 target hour를 기술하며 leakage-free임.
  Total feature width는 이제 25(15 lag/rolling + 10 calendar) plus 3 label.

## Commands verified

이 머신에서 실행함(Python 3.12.10 local; web/CI sandbox에서 Python 3.11.15 + Node 22로도 검증됨),
`.venv`:

- `ruff check .` — passed
- `ruff format --check .` — passed (95 files)
- `mypy .` — passed (no issues, 95 source files)
- `pytest` — **114 passed, 1 skipped** (skip은 optional QAOA test; qiskit 없음).
- `make rebalance-demo` (`python -m optimization.demo`) — offline; cutoff 15:30에서 greedy와
  MILP 둘 다 8 bike를 이동함(cost 42.0 → 17.70, shortage 8 → 0, feasible); enumeration optimum이
  MILP와 일치함; single-edge QUBO brute-force energy가 exact enumeration과 같음(match=True).
- `apps/web`: `npm run typecheck`와 `npm run build` — TS strict 하에서 passed(Next.js 15, Node 22).
- `make evaluate` (`python -m ml.forecasting.run <June zip>`) — offline; rolling-origin over
  30,947 usable row / 139 zone. CV WAPE 기준 best: **knn** (`n_neighbors=30`, `weights=distance`),
  test WAPE 0.516, MASE 0.794(B0 seasonal naive WAPE 0.658 / MASE 1.013을 이김). 6개 알고리즘 모두
  B0을 이김; top-12 reduced model이 full 32-feature model과 일치함. domain-customised OCS
  (shortage-weighted)는 순위를 재배열함(extra_trees best, knn worst learned model). Ablation
  B1=B2=B3=B4(event feature가 June window에서 0으로 verified). `README.md`와 `reports/phase06_*` 참조.
- `make graph-upsert-demo` — offline; 2 events → 15 nodes / 17 edges; idempotent replay; audit
  clean; event가 3개 H3 zone에 link됨.
- `make graph-features-demo` — offline; as-of boundary를 보여줌: cutoff 13:59 → 0 snapshot
  (transit event 아직 available 안 됨); 14:30 → 2 zone(transit_disruption_exposure ≈ 0.63);
  15:30 → 3 zone(concert가 available해지고 transit event가 decay하면서).
- 실제 June-2026 데이터에 대한 EDA(`docs/EDA.md`, `docs/STATISTICAL_TESTS.md`): 7개의
  leakage-safe feature 도출(surge momentum, zone expanding mean, same-day net-flow pressure, 그리고
  두 개의 member-share composition lag); feature width 이제 **32**.
- Statistical verification (scipy): weekday vs weekend는 **timing**(evening rush
  Cohen's d = 2.20)과 **rider composition**(member share d = 2.72, p = 1.4e-4)에 의해 구동되며,
  daily total에 의한 것이 아님(Welch p = 0.15). Day-of-week significant(Kruskal p = 0.017); rideable_type은
  rush에 대해 significant하지 않음(chi-square p = 0.50) → 의도적으로 feature로 추가하지 않음.
- Visual EDA report를 Artifact로 published함(offline, self-contained; chart + test).
- `make collect-demo` — 완전히 offline으로 실행됨(이전 phase output 참조).
- `make build-features` (`python -m pipelines.features.demo`) — sample fixture에서 offline:
  trips=4, demand_cells=7, feature_rows=7, zones=4.
- `make extract-events-demo` (`python -m pipelines.events.demo`) — offline; 3개 fixture
  article로부터: 2개 accepted event(TRANSIT_DISRUPTION → demand increase; LARGE_VENUE_EVENT), 0
  error, evidence grounded; neutral article은 event를 산출하지 않음.
- `make v2-evaluate-revenue` (`python -m ml.pricing.revenue_eval`) — offline; 실제 quote path에서
  flat vs event-aware dynamic revenue(SIMULATED SHADOW). Headline(elasticity 0.5): flat 362.00
  vs dynamic 363.40 → **+0.4% revenue, 0 lost rentals, 7 surcharged**; elasticity sweep flat
  (supply-constrained); event-severity what-if ×1/×2/×3 → uplift +0.4%/+1.0%/+1.5%, tier
  1.10×/1.25×/1.25×. Report `reports/v2/pricing/revenue_sim.json`.
- `python -m ml.forecasting.run` (no zip) — offline; crash하는 대신 정직한 **`blocked_data`**
  `reports/phase06_results.json`을 씀(sample에서 7-day warm-up 후 0 usable row), 그리고 real-run command를
  print함.

## Tests passing / failing

- Unit: `test_contracts.py` (19), `test_settings.py` (3), `test_temporal.py` (6),
  `test_demand_features.py` (12), `test_calendar.py` (5), `test_event_extraction.py` (9),
  `test_graph_features.py` (10, **14:01→14:00 leakage regression** 포함) — passing.
- Integration: `test_collectors.py` (8), `test_graph.py` (9), `test_api.py` (10 — HTTP를 통한
  as-of boundary, evidence-backed explanation, scenario toggle, **feasible rebalancing plan**) —
  passing.
- Rebalancing/optimization: `test_rebalancing.py` (6 — pure objective, feasibility rejection,
  greedy feasibility, MILP == enumeration and ≤ greedy, binding vehicle capacity), `test_qubo.py`
  (6 + 1 skipped — bounded encoding coverage, QUBO == surrogate energy, **QUBO == enumeration
  optimum**, crafted instance에서 QUBO == MILP plan, qiskit 없이 QAOA degrade).
- Forecasting: `test_forecasting.py` (10) — WAPE/MASE zero-denominator behaviour, seasonal-naive
  fallback, 그리고 모든 training fold가 자신의 validation window에 선행한다는 rolling-origin 보장
  (no temporal leakage, §11.3).
- Temporal coverage는 **DST spring-forward and fall-back** case(§5.3)와
  **lag/rolling leakage** 보장(§5.4)을 포함하며, "current value를 바꿔도 과거 feature는
  바뀌지 않는다"를 포함함.

## Measured results available

- `JC-202606-citibike-tripdata.csv.zip`(June 2026, §7.1에 따라 git-ignored)에 대한 **Real-data run**,
  전체 pipeline ~4.7s:
  - collection: total=109,897, accepted=109,510, excluded=387(전부 `missing_coordinate`, verified).
  - aggregation: **208개 H3 zone에 걸친 40,479 demand cell**.
  - features: 40,479 row; 30,947개가 1-week(168h) lag available.
  - busiest cell: 2026-06-09 17:00(evening rush) — departures=87, arrivals=13, net=-74.
- 동일 데이터에 대한 **Forecasting (Phase 06)**(rolling-origin, seed 42; `make evaluate`):
  - dev 26,918 / out-of-sample test 4,029 row(last 72h), 3 expanding CV fold, 32 B1 feature.
  - leaderboard (test WAPE): extra_trees 0.492, gradient_boosting 0.497, hist_gb 0.497,
    random_forest 0.505, knn 0.516, ridge 0.527; B0 seasonal naive 0.658. CV-selected model: knn.
  - permutation importance 기준 top feature: `dep_lag_1`, `dep_lag_168`, `arr_lag_1`, `dep_lag_24`,
    `cal_hour_cos`, `cal_is_evening_rush` — short-term persistence + weekly seasonality + rush timing.
  - **OCS (domain-customised, shortage-weighted 2:1)가 순위를 재배열함**: CV-WAPE pick인 knn이
    OCS에서 *worst* learned model(0.857)인데 대부분 under-forecast하기 때문; extra_trees가 OCS에서 best
    (0.781). 모든 model이 under-forecast(negative bias) → structural stockout risk.
  - event ablation은 B1로 collapse함: June의 last cutoff에서 0 graph snapshot(verified, §5.2).

## Known blockers / notes

- Local `.venv`는 Python 3.12.10을 사용함(repo는 `>=3.11` pin; 머신에 3.11 없음).
- News와 GBFS는 여전히 fixture/sample임(real news feed는 user가 연기; GBFS live는 opt-in).
- Console output은 Windows cp949 호환성을 위해 ASCII-only임.
- **June window에서 event lift를 demonstrate할 수 없음**: curated event가 trip data를 post-date하므로,
  as-of event/graph feature가 0이고 B2–B4 = B1임(verified, assume 아님).
  `docs/KNOWN_LIMITATIONS.md` 참조. `make evaluate CITIBIKE_ZIP=…`은 7-day-lag warm-up을 견디고
  rolling-origin holdout을 남길 만큼 충분히 깊은 실제 trip backfill에 대해 full B0–B4 ablation을 실행함;
  tiny sample fixture는 그 history가 없으므로, `ml/forecasting/run.py`는 이제 crash하거나 measured
  `reports/phase06_results.json`을 clobber하는 대신 별도 파일에 정직한
  **`blocked_data`** marker(fabricated metric 없음, exact real-run command print됨)를 씀.
- **Relational store (opt-in `[rdb]`)** — `services/db/`(SQLAlchemy Core)가 station
  network + inventory snapshot + load-audit trail을 **기본적으로 SQLite**(`make db-load`,
  zero-config, offline) 또는 `DATABASE_URL`을 통한 **Postgres**에 persist함 — 동일 코드, parameterized statement,
  idempotent upsert, non-destructive `init`. End-to-end verified: JSON
  fixture에서 45개 station이 resolved H3 zone과 함께 load됨, idempotent re-load. `tests/integration/test_db.py`(in-memory
  SQLite, extra 없으면 skip).
- **Live Neo4j graph (opt-in `[graph]`)** — `build_graph_store()` factory가 backend를 선택함:
  기본적으로 offline `InMemoryGraphStore`, `NEO4J_PASSWORD`가 설정되면 live `Neo4jGraphStore`
  (`make graph-upsert-neo4j`, `--backend neo4j`). `docker-compose.yml`이 local dev용 Neo4j(및
  Postgres)를 provision함. forecasting graph feature는 pure function이며 절대 graph DB에 의존하지 않음 —
  Neo4j는 §9 upsert/audit surface일 뿐. Factory selection은 unit-test됨
  (`tests/unit/test_graph_factory.py`); live-server path는 Docker가 필요함(in-sandbox에서 exercise 안 됨).
- **Real LLM event extraction (opt-in)** — deterministic mock과 함께 Claude-backed `AnthropicLlmProvider`
  (`pipelines/events/anthropic_provider.py`, `LLM_PROVIDER=anthropic`, `make evaluate … --provider
  anthropic`). Strict tool use를 통한 structured output; **evidence는 article의 exact substring일 때만
  유지됨**(ungrounded event drop); geocoding은 gazetteer를 통해 deterministic하게 유지됨(never model
  coordinate); severity/confidence clamp됨; 모든 extraction에 model id + prompt version. Demo Mode와 모든
  test는 mock default를 유지함; real provider는 lazy하며 SDK/key 없이 **per-article error로 degrade함
  (never fabricated event)**. `pip install anthropic` + `ANTHROPIC_API_KEY`(또는 `ant auth login`) 필요.
- **Real event-lift path is now fully wired**(이전에는 B2–B4 column이 0으로 hard-coded되었음):
  `load_real_panel(source, news_source=…)` / `python -m ml.forecasting.run <trip> --news <news.jsonl>`이
  real as-of graph feature를 ablation column에 join하며, leakage-safe함(H에 first available한 event는
  H 이전의 모든 row에 0을 기여 — `tests/unit/test_dataset_event_join.py`에 pin됨).
  `--news`가 없으면 column은 identically 0으로 유지됨(honest zero-overlap baseline). positive
  LLM-feature lift를 *measure*하려면 여전히 availability가 trip window와 overlap하고 V2-01 coverage gate를
  통과하는 news backfill이 필요함; 그 데이터는 이 offline sandbox에 없지만, code
  path는 공급되는 순간 real B2–B4 feature를 생성함.

## Known blockers / notes (Phase 08)

- `qiskit`이 이 환경에 설치되어 있지 않음; QAOA path는 그 "unavailable" branch로만 exercise되고
  그 test는 문서화된 reason과 함께 skip됨(§14.2). Quantum Research Mode의 나머지 모든 것
  (QUBO build + brute-force + enumeration validation)은 그것 없이 실행됨.
- rebalancing station inventory는 curated fixture(`data/fixtures/rebalancing_demo.json`)임;
  target은 measured Phase 06 model이 아니라 label된 demo heuristic을 사용함.
  `docs/KNOWN_LIMITATIONS.md` 참조.

## Next phase input contract

**Phase 09 — Final Audit & Portfolio Packaging**은 완료된 Phases 00–08을 consume하고:
- documentation을 implementation에 sync함(`docs/PRD.md`, `ARCHITECTURE.md`, `DATA_CONTRACTS.md`,
  `GRAPH_SCHEMA.md`, `OPTIMIZATION.md`, `DEMO_SCRIPT.md`, `EVALUATION_PROTOCOL.md`,
  `KNOWN_LIMITATIONS.md`, `STATUS.md`, `README.md`).
- final honesty audit를 실행함(fabricated metric 없음, feature attribution으로부터의 causal claim 없음,
  quantum-advantage claim 없음, fixture vs live vs measured가 명확히 구분됨) with full gate
  green, §18과 §23에 따라.
