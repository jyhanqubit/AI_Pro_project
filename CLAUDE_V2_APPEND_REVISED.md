# ShockFlow AI V2 Addendum — Revised Business Value Plan

This addendum extends the root `CLAUDE.md` operating contract. It is imported from `CLAUDE.md`
via `@CLAUDE_V2_APPEND_REVISED.md`. Everything in the base contract (temporal correctness,
leakage prevention, honesty invariants, mode separation) still applies unchanged. This file
adds the V2-specific obligations on top of it.

## V2 Mission

V2 is not a feature-expansion release. It is an **LLM net-business-value verification** release.

```text
Measured model productization
→ H3 multi-holdout
→ Rule vs LLM event ablation
→ Profit / Regret Ledger
→ MPC / bounded pricing
→ GraphRAG correctness benchmark
→ artifact-backed product UI
```

## Domain

```text
ShockFlow AI
Citi Bike / New York City
Station / H3 Zone / Borough
```

Do not invent a Seoul / Gwanak / ParcelFlow / parcel-logistics contract. The domain stays
Citi Bike / NYC.

## Source of Truth

```text
1. current command/test result
2. versioned artifact
3. code and contract
4. current docs
5. old handoff
```

Never copy numbers from stale documents verbatim. A number is only quotable if a current
command, test, or versioned artifact produces it.

## V2 Required Evidence

```text
1. promoted measured model is served
2. H3 multi-holdout report exists
3. No Event / Rule Event / LLM Event are separated
4. predictive lift is translated into profit/regret
5. LLM incremental cost is included
6. GraphRAG correctness and relevance are evaluated
7. all UI metrics point to artifacts
```

## Profit Integrity

- Separate contribution margin from shortage externality.
- Do not double-count lost margin with shortage cost.
- Manage cost and elasticity as a **versioned assumption set**.
- The Oracle policy is an offline upper bound only.

## Mandatory Policies

```text
No Action
Greedy
Single-period MILP
MPC
```

SP / CVaR are optional.

RL and QAOA are research-only and are **not** V2 completion conditions.

## LLM Boundaries

The LLM is used only for event structuring, tool routing, and explanation.

The LLM does not directly compute demand, price, or profit numbers.

A numeric Copilot answer is rejected if there is no typed tool result behind it.

## Claims

```text
measured
offline_benchmark
simulated
pending_live_label
assumption
blocked_data
blocked_external
demo_fixture
research
```

Every API / UI result includes `run_id`, `artifact_id`, `mode`, `claim_status`, and `freshness`.

## Productization

- Demo heuristics are allowed only in `demo_fixture`.
- Non-demo modes use the promoted measured model artifact.
- UI metrics are never hard-coded.
- Do not expose search-index quantities/prices directly; hydrate them from the operational ledger.
- Elasticsearch is an optional adapter, not a required dependency.

## Phase Order

```text
V2-00 Audit & Domain Correction
V2-01 Measured Model Productization & H3 Multi-Holdout
V2-02 Profit / Regret Ledger
V2-03 LLM Incremental Value Ablation
V2-04 Multi-period MPC Decisioning
V2-05 Dynamic Pricing & Experiment Dry-run
V2-06 GraphRAG Decision Copilot Benchmark
V2-07 Operator Cockpit & Rider Preview
V2-08 Persistence, Monitoring & Delayed Labels
V2-09 Final Audit & Portfolio Packaging
```

## Completion Rule

Completion is judged by the following artifacts, not by feature existence.

```text
H3 holdout metrics
profit/regret ledger
LLM incremental value report
MPC policy comparison
pricing sensitivity and guardrail audit
Copilot correctness benchmark
final claim matrix
```
