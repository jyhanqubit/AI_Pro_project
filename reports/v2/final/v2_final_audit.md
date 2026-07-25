# V2-09 — Final Audit & Portfolio Packaging

_Phase: **V2-09**. Status: **PASSED — V2_COMPLETE**. 재현: `make v2-final` (exit 0 = pass)._
_범위: 완성된 포트폴리오를 **committed artifact 기준으로** 판정 (addendum "Completion Rule"). 이 audit은
아무것도 재측정하지 않고 `reports/v2/**`를 읽어 machine-checkable gate 4개를 강제합니다. machine mirror는
`reports/v2/final/claim_matrix.json`, 서술형 matrix는 `docs/v2/V2_CLAIMS_MATRIX.md`, 알고리즘 원리+metric은
`docs/v2/V2_ALGORITHMS.md`._

---

## Gate 결과 (`scripts/v2_final_audit.py`가 machine-check)

| # | Gate | 결과 | 검사 방식 |
|---|---|---|---|
| 1 | **Envelope 표기 검증** — committed V2 artifact마다 result-envelope field를 갖고 `contracts.v2.ResultEnvelope`로 validate | **PASS** (31개) | artifact마다 `ResultEnvelope`를 생성; 잘못 라벨된 status(예: research 모드가 아닌데 `research`)나 값을 가진 `blocked_*` artifact는 여기서 실패 |
| 2 | **Completion artifact** — completion rule이 요구하는 artifact가 전부 존재 | **PASS** | 필수 artifact 7개 존재 확인 |
| 3 | **Traceability** — artifact가 스스로 선언한 `artifact_id` 경로가 disk에 존재 | **PASS** | `#pointer`를 떼고 파일 존재 확인 |
| 4 | **Claim matrix 생성** | **PASS** | 모든 artifact + headline metric을 `claim_matrix.json`에 mirror |

**claim_status별 artifact 수:** `measured` 16 · `offline_benchmark` 7 · `simulated` 5 ·
`blocked_data` 1 · `demo_fixture` 1 · `research` 1  (총 **31**).

---

## Completion-rule coverage (addendum)

| 필수 artifact | 파일 | Headline (artifact에서 추출) |
|---|---|---|
| H3 holdout metrics | `holdout/h3_multiholdout.json` | WAPE **0.4823**, MASE **0.821** (MASE<1 ⇒ seasonal-naive를 이김) |
| Profit/regret ledger | `ledger/profit_regret.json` | no-action 대비 net **+$103,271**; Oracle 대비 regret **$218,697** (`simulated`) |
| LLM incremental value report | `llm_value/incremental_value_borough.json` | structured lift **measured_improvement**; LLM-news **negative_lift**, net **−$17,789** |
| MPC policy comparison | `mpc/policy_comparison.json` | MPC total_cost **740.3**, regret **21.6** (best feasible) |
| Pricing sensitivity | `pricing/sensitivity.json` | A/A CI가 0 포함 (유효한 null 설계) |
| Pricing guardrail audit | `pricing/guardrail_audit.json` | 위반 **0**, budget 준수 |
| Copilot correctness benchmark | `copilot/correctness_benchmark.json` | routing **1.0**, hallucination **0**, hard gate **pass** |
| Final claim matrix | `final/claim_matrix.json` | 이 run |

함께 committed된 보조 benchmark: GraphRAG relevance + neutral text-lookup control, RAGAS retrieval +
generation (faithfulness **1.0**, answer_relevancy **0.985**), trip-plan faithfulness (**1.0**, ungrounded
0), monitoring run-manifest + delayed-label loop.

---

## 결과 표기 원칙 (이 포트폴리오가 주장하는 것과 안 하는 것)

- **Measured 승리:** promoted forecaster가 rolling H3 multi-holdout에서 seasonal-naive를 이김; **structured
  event feed**가 measured accuracy lift를 줌; Copilot이 typed tool로 routing하며 **numeric hallucination 0**.
- **null (핵심 발견):** 이 데이터에서 **LLM-from-news feature는 수요 예측을 개선하지 않음** — LLM
  Feature Value metric + CI로 보고하고, root cause를 규명(dense + precise-time + precise-location +
  forward-looking; news는 하나도 만족 못 함)했으며, *simulated* synthetic ceiling(+10.43%)으로 위쪽 경계를
  잡음(조건을 만족하면 방법 자체는 동작). `docs/v2/V2_WHY_LLM_FEATURES.md` 참고.
- **Simulated이지 measured 아님:** 모든 금액(ledger, MPC, pricing)은 assumption에 조건부이고 `simulated`로
  라벨; 단위 수량만 measured.
- **Research 전용, completion gate 제외:** RL(tabular Q-learning + PPO)과 QAOA. RL은 흥미 목적상 같은 ledger로
  채점 — **PPO 202.9 > tabular 247.8, 둘 다 MPC 21.6에는 못 미침; RL advantage 주장 안 함**.
  `ResultEnvelope` validator가 모든 research 값을 product surface에서 차단.
- **Blocked이지 faked 아님:** H3-grain graph test는 `blocked_data` (event가 borough-tag만 있고 lat/lng 없음)
  — 기록만 하고 조작하지 않음.

---

## V2-09 acceptance 체크리스트

- [x] 31개 committed artifact 전부에서 envelope 표기 검증 gate green (`make v2-final` gate 1)
- [x] completion-rule artifact 7개 전부 존재 (gate 2)
- [x] 모든 artifact가 disk 경로로 traceable (gate 3)
- [x] `reports/v2/final/claim_matrix.json`을 committed artifact에서 재생성
- [x] `docs/v2/V2_ALGORITHMS.md`가 각 알고리즘의 원리 + metric 문서화
- [x] Unit test: `tests/unit/test_v2_final_audit.py` (gate 통과 + mislabel 잡힘)

**V2-09 verdict: PASSED — V2_COMPLETE.** completion rule이 committed artifact로 충족됨. RL/QAOA는 research
전용이라 gate 밖입니다.
