# ShockFlow AI — V2 Documentation Index

V2는 **LLM net-business-value verification** 릴리스이다. 새로운 도메인이나 투기적 기능을
추가하지 않는다; 대신 LLM/event 파이프라인이 측정 가능한 predictive lift를 만들어 내는지,
그리고 그 lift가 운영 profit으로 전환되는지를 versioned artifact로 증명한다.

> 이 폴더의 모든 V2 문서 상태: **PLAN / TEMPLATE**. 아직 measured V2 수치는 존재하지 않는다.
> 모든 result 셀은 실제 command나 artifact가 값을 생성하기 전까지 `pending`으로 표시된다. 운영
> 계약에 따라 fabricated metrics는 금지된다 — result 테이블을 오래된 v1 수치나 추정치로 채우지
> 말 것.

Read order: base contract `../../CLAUDE.md` → V2 addendum `../../CLAUDE_V2_APPEND_REVISED.md`
→ `V2_MISSION.md` → `V2_EXECUTION_PLAN.md` → 아래의 영역별 문서.

## Documents

| Doc | Purpose | Backing phase(s) |
|---|---|---|
| `V2_MISSION.md` | V2 mission, domain, source-of-truth, required evidence, invariants | all |
| `V2_EXECUTION_PLAN.md` | Phase V2-00 … V2-09: goal, acceptance criteria, artifact, command | all |
| `V2_CLAIMS_MATRIX.md` | Claim taxonomy + result envelope (`run_id`/`artifact_id`/`mode`/`claim_status`/`freshness`) | V2-00, V2-09 |
| `V2_EVALUATION_PROTOCOL.md` | H3 multi-holdout evaluation design | V2-01 |
| `V2_PROFIT_REGRET_LEDGER.md` | Profit/regret accounting, integrity rules, assumption set | V2-02 |
| `V2_LLM_VALUE_ABLATION.md` | No-Event / Rule-Event / LLM-Event separation + incremental cost | V2-03 |
| `V2_MPC_DECISIONING.md` | Mandatory policy comparison (No Action / Greedy / MILP / MPC) | V2-04 |
| `V2_PRICING.md` | Bounded dynamic pricing + experiment dry-run + guardrail audit | V2-05 |
| `V2_PRICING_EXPLAINED.md` | Plain-language primer: elasticity, surge, A/A experiment | V2-05 |
| `V2_GRAPHRAG_COPILOT.md` | GraphRAG Decision Copilot correctness/relevance benchmark | V2-06 |
| `V2_KNOWN_LIMITATIONS.md` | Honest V2 limitations, blocked data/external, research-only scope | V2-09 |

## V2용으로 생성된 폴더 구조

```text
docs/v2/                V2 planning docs (this folder)
contracts/v2/           V2 typed contracts (result envelope, ledger, policy compare) — package stub
config/v2/              V2 config (assumption sets, holdout windows, guardrails) — stub
data/fixtures/v2/       V2 offline fixtures — stub
reports/v2/holdout/     V2-01 H3 multi-holdout artifacts
reports/v2/ledger/      V2-02 profit/regret ledger artifacts
reports/v2/llm_value/   V2-03 LLM incremental value report
reports/v2/mpc/         V2-04 MPC policy-comparison artifacts
reports/v2/pricing/     V2-05 pricing sensitivity + guardrail audit
reports/v2/copilot/     V2-06 Copilot correctness benchmark
reports/v2/final/       V2-09 final claim matrix + run manifest
```

## Completion rule (addendum 기준)

V2는 다음 artifact들이 존재하고 real일 때에만 완료된다:

```text
H3 holdout metrics
profit/regret ledger
LLM incremental value report
MPC policy comparison
pricing sensitivity and guardrail audit
Copilot correctness benchmark
final claim matrix
```
