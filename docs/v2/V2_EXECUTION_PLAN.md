# V2 Execution Plan — Phases V2-00 … V2-09

아래 각 phase는 **goal · acceptance criteria · completion artifact · reproduction command**를 나열합니다.
Phase gate는 준수됩니다: acceptance criteria가 충족되고, 관련 test가 통과하고,
docs가 실제 동작을 반영하고, 출력이 real일 때까지 진행하지 마십시오. `Status`는 모든 phase에서 `PLANNED`로 시작하며,
실행된 command나 커밋된 artifact로부터만 갱신하십시오.

`Status` 범례: `PLANNED` → `IN_PROGRESS` → `PASSED` / `PASSED_BLOCKED_*` / `BLOCKED`.

---

## V2-00 — Audit & Domain Correction
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** repo를 V2 addendum과 대조하여 조정; 도메인이 모든 곳에서 Citi Bike / NYC임을 확인;
  어떤 v1 artifact가 재사용 가능한지 vs 재측정해야 하는지 목록화; result envelope 정의.
- **Acceptance:** active code/docs에 Seoul/ParcelFlow/parcel 참조 없음; `claim_status`
  envelope이 `contracts/v2/`에 정의됨; stale-number audit이 모든 doc 수치와 그 출처를 나열함.
- **Artifact:** `reports/v2/final/v2_audit.md` (audit table) + envelope contract committed.
- **Command:** `make v2-audit` → exit 0 (2 gates PASS). Envelope tests: `pytest tests/unit/test_v2_envelope.py` → 22 passed.
- **Delivered:** `contracts/v2/{enums,envelope}.py` (`ClaimStatus` 9-value + `ResultEnvelope`);
  `scripts/v2_audit.py`; `reports/v2/final/v2_audit.md`. 발견 사항: 도메인 clean (0 drift);
  JC-vs-NYC 뉘앙스 기록; test-count 불일치(docs 전반에 걸쳐 114/199/200/204) 및
  legacy `v2-*` phase-number 충돌을 flag함.

## V2-01 — Measured Model Productization & H3 Multi-Holdout
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** measured forecasting model artifact를 promote하고 non-demo mode에서 serve;
  단일 split이 아니라 여러 rolling H3 holdout window에 걸쳐 평가.
- **Acceptance:** promoted model manifest가 API에서 참조됨; ≥3 rolling-origin holdout
  window에 대해 window별 및 aggregate WAPE/MAE/MASE 보고; random split 없음; leakage test 통과.
- **Artifact:** `reports/v2/holdout/h3_multiholdout.json` + `promoted_model.json` + `README.md`.
- **Command:** `make v2-holdout`. `V2_EVALUATION_PROTOCOL.md` 참조.
- **Delivered (measured):** `ml/forecasting/h3_multiholdout.py` (runner) + `promoted.py` (serving
  loader). Real JC Citi Bike Mar–Aug 2024, 210,042 H3 rows / 234 zones, 3 rolling monthly windows.
  Promoted `hist_gradient_boosting`; aggregate **WAPE 0.4828 ± 0.0030, MASE 0.7996** (매 window에서
  B0 seasonal-naive ~0.648을 이김). Leakage guard + window/aggregate tests:
  `pytest tests/unit/test_v2_multiholdout.py` → 5 passed.
- **Scope / carry-forward:** JC slice (NYC 전역 아님); B1 (demand+calendar) feature만
  (events B2–B4 = V2-03); promotion pool은 `ridge`+`hist_gradient_boosting`으로 제한됨
  (`--algos all` = full zoo); API serving wiring는 **V2-07**에 도착(loader contract는 지금 준비됨).

## V2-02 — Profit / Regret Ledger
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** forecast error를 돈으로 환산: expected shortage cost, overflow cost,
  relocation cost, 그리고 Oracle upper bound 대비 regret.
- **Acceptance:** contribution margin과 shortage externality를 분리 유지; lost margin의
  double-count 없음; assumption을 versioned `config/v2/` assumption set에서 로드; Oracle을
  offline upper bound로 라벨링.
- **Artifact:** `reports/v2/ledger/profit_regret.json` + `reports/v2/ledger/README.md`.
- **Command:** `make v2-ledger`. `V2_PROFIT_REGRET_LEDGER.md` 참조.
- **Delivered:** `optimization/ledger.py` (pure accounting) + `ledger_run.py` (runner) +
  `contracts/v2/ledger.py` (typed) + `config/v2/assumptions.yaml` (`v2-assumptions-1`).
  결과: promoted forecast는 114,079 zone-hour decision에 걸쳐 seasonal-naive 대비 **+$103,271**를
  net함(부호는 9개 cost setting 모두에서 robust), Oracle 대비 regret **$218,697**. Units는 measured, dollars는
  `simulated`. Tests: `pytest tests/unit/test_v2_ledger.py` → 8 passed (no-double-count, Oracle
  upper-bound/regret≥0, better-forecast-earns-more).
- **Scope / carry-forward:** single-period **stocking** economics만 — **relocation = 0**
  (origin→destination moves = V2-04 MPC); dollars는 assumption이 sourcing될 때까지 `simulated`로 유지.

## V2-03 — LLM Incremental Value Ablation
- **Status:** ✅ PASSED (2026-07-20) — null result (`insufficient_event_overlap`)
- **Goal:** **No-Event**, **Rule-Event**, **LLM-Event** feature set을 분리하고 각각의
  incremental predictive lift와 incremental profit을 측정 — LLM cost 차감 후.
- **Acceptance:** 세 ablation arm이 동일한 cutoff/split을 공유; lift를 CI와 함께 보고;
  LLM incremental token/$ cost 포함; LLM이 rule arm 대비 lift를 더하지 않으면 그대로 보고.
- **Artifact:** `reports/v2/llm_value/incremental_value.json` + `README.md`.
- **Command:** `make v2-llm-value`. `V2_LLM_VALUE_ABLATION.md` 참조.
- **Delivered:** `ml/forecasting/llm_value.py` (3-arm A0=B1/A1=B2/A2=B4, shared promoted model +
  splits, block-bootstrap CI, ledger profit, LLM cost model). Real JC 2026 H1 + real GDELT NYC
  2026 news (371 articles). **결과:** 모든 arm 동일, ΔWAPE=0 CI[0,0], event coverage 0.3%
  → **`insufficient_event_overlap`** (`blocked_data`); LLM actual $0 (mock), est real $0.0061,
  **net LLM value −$0.01**. Tests: `pytest tests/unit/test_v2_llm_value.py` → 6 passed.
- **Borough re-measurement (NYC), the FAIR test:** `ml/forecasting/llm_value_borough.py`
  (`make v2-llm-value-borough`)는 **19.9M real NYC trips**를 borough×hour로 스트리밍하고 5-month
  training (Jan–Apr), citywide news attribution (4→35 articles), **May** testing(June의 window는
  attributable news가 0; May는 216 news rows 보유). Arms A0 / A1 (+permitted) / A2 (+LLM news):
  **A1−A0 = measured_improvement** (WAPE 0.1069→0.1047, CI [1.87, 5.88], +$33k — structured event가
  도움이 됨, v1을 robust하게 재현); **A2−A1 = negative_lift** (WAPE 0.1047→0.1075, CI [−6.02, −3.71],
  **net LLM value −$23,730**). Tests: `tests/unit/test_v2_llm_value_borough.py` → 4 passed.
- **Real-LLM extraction (decisive):** mock-quality confound를 제거하기 위해, claude-opus-4-8(이
  세션)이 371 articles로부터 clean하고 grounded된 NYC event 23개를 직접 추출함
  (`data/fixtures/news_live/claude_events_2026h1.jsonl`; `--claude-events` path). 재실행(test May,
  336 clean news rows): A1−A0 **measured_improvement** (0.0908→0.0883, CI [1.08,6.71]); A2−A1
  **여전히 negative_lift** (0.0883→0.0905, CI [−5.32,−1.56], net LLM value −$17,789).
- **V2 answer (this data):** **structured permitted-event feed은 돈의 가치가 있음**;
  **news로부터의 LLM layer는 real high-quality LLM extraction으로도 net-negative** — news
  event는 sparse하고, temporally coarse하며, dense한 official permitted schedule과 redundant하여
  signal이 아니라 variance를 더함. 이 negative는 extraction-quality artifact가 아님. Caveat:
  borough event effect는 작고(~0.002 WAPE) sample-sensitive함; geo-precise하고
  higher-frequency한 event를 가진 finer grain이라면 더 강한 test가 됨(이 news corpus에서는 이용 불가).

## V2-04 — Multi-period MPC Decisioning
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** ledger objective에 대해 multi-period horizon에 걸쳐 4개의 mandatory policy를 비교.
- **Acceptance:** `No Action`, `Greedy`, `Single-period MILP`, `MPC`가 모두 동일한
  instance에서 실행됨; 모든 plan이 feasibility-check됨; infeasibility가 명시적으로 보고됨; MPC는
  future truth가 아니라 forecast horizon을 사용함.
- **Artifact:** `reports/v2/mpc/policy_comparison.json` + `README.md`.
- **Command:** `make v2-mpc`. `V2_MPC_DECISIONING.md` 참조.
- **Delivered:** `optimization/mpc.py` (greedy/MILP solver를 재사용하는 receding-horizon simulator) +
  `mpc_run.py`. 결과 (8 zones, 72h, seeded scenario, ledger cost — 낮을수록 좋음): No Action
  1126.7 / Greedy 1154.7 / MILP 1086.9 / **MPC 740.3** / Oracle 718.7. **MPC best feasible**
  (Oracle 대비 regret 21.6, ~3%); single-period 대비 shortage+overflow를 반으로 줄임; 여기서 Greedy는 net-harmful.
  MPC는 forecast만 사용(no leakage); Oracle = offline bound (regret ≥ 0); 모두 feasible.
  Dollars `simulated`. Tests: `pytest tests/unit/test_v2_mpc.py` → 7 passed.

## V2-05 — Dynamic Pricing & Experiment Dry-run
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** guardrail을 가진 bounded incentive/pricing policy + offline experiment dry-run.
- **Acceptance:** price bound가 강제됨; elasticity는 versioned assumption set에서; guardrail
  audit (bound를 벗어난 price 없음, negative-margin action 없음); experiment는 `simulated`로 라벨링
  (real user 없음 → causal lift claim 없음).
- **Artifact:** `reports/v2/pricing/sensitivity.json` + `reports/v2/pricing/guardrail_audit.json`.
- **Command:** `make v2-pricing`. `V2_PRICING.md` 참조.
- **Delivered:** `ml/pricing/pricing_v2_eval.py` (bounded policy + guardrail audit, assumption에서
  온 elasticity, ledger objective) + `pricing_v2_run.py`. 576 seeded zone-hours: **0 guardrail
  violations**, safety zone은 base-fare, budget 0/40 준수, **negative control**이 심어진
  out-of-bounds surge를 잡아냄; sensitivity grid (elasticity × surge-bound); **A/A switchback**
  effect ≈ 0, CI가 0을 포함(design valid). 모두 `simulated`. Tests:
  `pytest tests/unit/test_v2_pricing.py` → 7 passed.

## V2-06 — GraphRAG Decision Copilot Benchmark
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** GraphRAG + typed tool을 통해 operator 질문에 답하는 Copilot; 그 correctness와
  retrieval relevance를 benchmark.
- **Acceptance:** typed tool result 없는 numeric answer는 rejected; correctness와 relevance를
  fixed offline question set에 대해 채점; 모든 answer가 provenance를 담음.
- **Artifact:** `reports/v2/copilot/correctness_benchmark.json` + report md.
- **Command:** `make v2-copilot`. `V2_GRAPHRAG_COPILOT.md` 참조.
- **Delivered:** typed tools (`ml/copilot/tools.py`) + router/Copilot (`copilot.py`) + benchmark
  (`benchmark.py`). 15-Q fixed set: routing 1.0, correctness 1.0, refusal 1.0, grounded 1.0,
  **ungrounded_numeric=0, hallucinated=0 (hard gates pass)**. 숫자는 committed된 V2 artifact를
  읽는 typed tool에서만 나옴; router는 절대 숫자를 생성하지 않음 -> grounding은 설계상 보장됨.
  Tests: `pytest tests/unit/test_v2_copilot.py` -> 7 passed.

## V2-07 — Operator Cockpit & Rider Preview
- **Status:** ✅ PASSED — artifact 기반 metrics API + cockpit UI + rider preview, 실행 중인 app에 대해 검증됨.
- **Goal:** **모든 metric이 artifact를 가리키는**(`run_id`/`artifact_id`) product UI,
  그리고 rider-facing preview.
- **Acceptance:** hard-coded UI metric 없음; 노출된 각 숫자가 `reports/v2/**`
  artifact로 resolve됨; demo heuristic은 `demo_fixture`에서만; live/replay/research가 시각적으로 구분됨.
- **Delivered:** `services/api/v2_metrics.py` (`cockpit_metrics()`) + endpoint
  `GET /v2/cockpit/metrics` — 모든 headline metric (holdout WAPE, served model, profit lift, best
  policy, MPC regret, guardrail violations, LLM-news value)이 committed된
  `reports/v2/**` artifact에서 live로 읽혀 `ResultEnvelope`로 감싸짐
  (`run_id`/`artifact_id`/`mode`/`claim_status`/`freshness`). `research` 결과는 product surface에서
  제외됨(envelope-enforced); 누락된 artifact는 blocked envelope로 표면화됨
  (`value=None`), 절대 가짜 숫자로 표시되지 않음. 4 test가 각 값을 그 artifact에서 다시 읽어 hard-coding이
  없음을 보장함 (`tests/unit/test_v2_cockpit_metrics.py`).
- **Cockpit UI delivered:** `apps/web/app/cockpit/page.tsx` (+ `/cockpit` nav tab, typed client
  `api.cockpitMetrics`)가 각 metric을 `GET /v2/cockpit/metrics`로부터 **claim_status
  badge**(측정됨/시뮬레이션/…)와 **artifact + run_id provenance**와 함께 렌더링함; hard-coded 숫자 없음; blocked된
  metric은 "artifact 없음"을 보여줌, 절대 가짜 값을 보여주지 않음; `ModeBadge`가 surface mode를 표시함.
- **Verified end-to-end (both surfaces):** `make api` + `make web` (Next.js dev)를 실행하고 headless
  Chromium을 통해 실제 렌더를 캡처함:
  - **Operator cockpit** — `docs/screenshots/v2_cockpit.png`: 모든 7 metric이 API에서 live로 오며
    claim badge (측정됨/시뮬레이션) + artifact/run_id provenance와 historical_replay mode badge를 가짐.
    화면에 hard-coded 숫자 없음.
  - **Rider preview** — `docs/screenshots/v2_rider.png`: as-of
    availability, rider copilot (규칙 기반/rule-based로 라벨링), event-surge marker, 그리고
    historical_replay mode badge를 가진 consumer view (`/`, rider role); demo/replay data, 조작된 live claim 없음.
  - **Rider trip planner** — `docs/screenshots/v2_rider_trip.png`: "A에서 B까지" → walk → rent → bike
    → return → walk. `services/api/trip_planner.py` (`POST /v2/rider/plan-trip`)가 가장 가까운
    rentable/returnable station을 선택하고 straight-line distance/time으로 leg를 배치함 — **모든
    숫자는 deterministic하며, 절대 LLM에서 오지 않음**. LLM의 역할 (V2-06에 따라): NL
    request를 origin/destination으로 파싱 + narrate; 여기서는 rule-based (`answer_mode`), key가 configured되면 LLM parser가
    `resolve_endpoints`에 slot-in됨. Live 검증됨: "시청에서 뉴포트" → rent City Hall
    (6) → 🚲 5min/1173m → return Newport (10). 7 tests (`test_v2_trip_planner.py`).
    - **LLM-parse benchmark** (`ml/copilot/trip_parse_benchmark.py`, `make v2-copilot`에 포함): NL
      parse가 LLM seam임. 10-query set (method-independent gold)에서 rule-based는 **0.6**,
      in-session LLM은 **1.0** — LLM은 정확히 어려운 case에서 이김(typos `뉴포뜨`/`시쳥`,
      negation `익스체인지 말고`, origin-stated-last `출발은 시청`). LLM parse는
      `data/fixtures/v2/trip_parse_claude.jsonl`에 audit용으로 committed됨; `offline_benchmark`. 이것은 V2-06
      lesson (intent understanding이 LLM의 measured value)을 planner에 적용한 것.
    - **Numeric faithfulness / no-hallucination** (`ml/copilot/trip_faithfulness.py`,
      `make v2-copilot`에 포함): answer의 모든 숫자가 typed
      plan에 grounded되어 있는지에 대한 RAGAS-style check(distance는 real station coordinate로부터 haversine으로 계산됨, 절대 LLM-generated가 아님).
      5 plan에 걸쳐 **mean_faithfulness 1.0, 0 ungrounded numbers**; negative control (injected
      `999`)이 잡히므로, LLM narrator가 template을 대체하더라도 guard가 hallucinated 숫자를 flag함.
      V2-06 `ungrounded_numeric=0`과 동일한 보장.
- **Status:** PASSED — artifact 기반 metrics API + envelope enforcement + cockpit UI + rider
  preview, 모두 실행 중인 app에 대해 검증됨.
- **Command:** `make web` (+ `make api`)가 V2 artifact를 구동.

## V2-08 — Persistence, Monitoring & Delayed Labels
- **Status:** ✅ PASSED (drift = `blocked_data`, no live labels — 명시됨)
- **Goal:** run/artifact를 persist; served model을 monitor; delayed live label을 연결하여
  `pending_live_label` → `measured` loop를 닫음.
- **Acceptance:** run manifest와 함께 artifact persist됨 ✅; monitoring이 freshness를 표면화함 ✅ (drift는
  live label stream이 필요 → `blocked_data`, 조작되지 않음); delayed-label backfill이 과거 cutoff로 누수되지
  않음 ✅ (strict `available_at > forecast_cutoff` guard, boundary 포함 unit-tested).
- **Delivered:** `ml/monitoring/run_manifest.py` (모든 26 `reports/v2/**` artifact를 run_id,
  claim_status, freshness, staleness와 함께 인덱싱) + `ml/monitoring/delayed_labels.py` (leakage-safe
  pending→measured loop). Artifacts `reports/v2/monitoring/{run_manifest,delayed_labels}.json`.
  5 tests (`tests/unit/test_v2_monitoring.py`). `V2_MONITORING.md` 참조.
- **Command:** `make v2-monitor`.

## V2-09 — Final Audit & Portfolio Packaging
- **Status:** PLANNED
- **Goal:** final audit; claim matrix 생성; V2 story 패키징.
- **Acceptance:** 모든 completion-rule artifact가 존재하며 real임; `V2_CLAIMS_MATRIX.md`가
  artifact로부터 채워짐; `V2_KNOWN_LIMITATIONS.md`가 최신; README/demo가 implementation과 일치.
- **Artifact:** `reports/v2/final/claim_matrix.json` + `reports/v2/final/run_manifest.json`.
- **Command:** `make v2-audit` (final pass).

---

## Completion checklist (from the addendum)

- [ ] H3 holdout metrics — `reports/v2/holdout/`
- [ ] profit/regret ledger — `reports/v2/ledger/`
- [ ] LLM incremental value report — `reports/v2/llm_value/`
- [ ] MPC policy comparison — `reports/v2/mpc/`
- [ ] pricing sensitivity + guardrail audit — `reports/v2/pricing/`
- [ ] Copilot correctness benchmark — `reports/v2/copilot/`
- [ ] final claim matrix — `reports/v2/final/`

> 위에 명명된 `make` target은 아직 구현되지 않은 **planned** 상태입니다. base contract에 따라,
> 의미 있고 tested된 workflow를 실행할 수 있을 때까지 target을 추가하지 마십시오.
