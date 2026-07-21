# ShockFlow AI — V2 Documentation Index

V2 is the **LLM net-business-value verification** release. It does not add new domains or
speculative features; it proves — with versioned artifacts — whether the LLM/event pipeline
produces measurable predictive lift, and whether that lift converts into operational profit.

> Status of every V2 doc in this folder: **PLAN / TEMPLATE**. No measured V2 numbers exist yet.
> All result cells are marked `pending` until a real command or artifact produces them. Per the
> operating contract, fabricated metrics are prohibited — do not fill result tables from stale
> v1 numbers or estimates.

Read order: base contract `../../CLAUDE.md` → V2 addendum `../../CLAUDE_V2_APPEND_REVISED.md`
→ `V2_MISSION.md` → `V2_EXECUTION_PLAN.md` → the per-area docs below.

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

## Folder scaffolding created for V2

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

## Completion rule (from the addendum)

V2 is complete only when these artifacts exist and are real:

```text
H3 holdout metrics
profit/regret ledger
LLM incremental value report
MPC policy comparison
pricing sensitivity and guardrail audit
Copilot correctness benchmark
final claim matrix
```
