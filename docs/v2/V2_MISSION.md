# V2 Mission & Contract

_Source: `CLAUDE_V2_APPEND_REVISED.md` (imported by `CLAUDE.md`). This doc is the human-readable
expansion; the addendum is authoritative if they ever diverge._

## 1. Mission

V2 is not a feature-expansion release. It is an **LLM net-business-value verification** release.
The single question V2 must answer with evidence:

> Do LLM-extracted events produce measurable predictive lift over calendar/history and over a
> plain rule baseline, and does that lift convert into operational profit after the LLM's own
> incremental cost is subtracted?

Value chain:

```text
Measured model productization
→ H3 multi-holdout
→ Rule vs LLM event ablation
→ Profit / Regret Ledger
→ MPC / bounded pricing
→ GraphRAG correctness benchmark
→ artifact-backed product UI
```

## 2. Domain (unchanged)

```text
ShockFlow AI · Citi Bike · New York City
grain: Station / H3 Zone / Borough
```

Do **not** introduce a Seoul / Gwanak / ParcelFlow / parcel-logistics contract. Domain stays
Citi Bike / NYC. This is an explicit correction target for V2-00.

## 3. Source of truth (priority order)

```text
1. current command / test result
2. versioned artifact (reports/v2/**)
3. code and contract
4. current docs
5. old handoff
```

Stale numbers are never copied verbatim. A number is quotable only if a current command, test,
or versioned artifact produces it. This applies especially to v1 numbers (e.g. WAPE figures in
`../V2_HANDOFF_REPORT.md`) — they describe v1 and must be re-measured before any V2 doc quotes
them.

## 4. Required evidence (the 7 gates)

| # | Evidence | Owning phase | Artifact |
|---|---|---|---|
| 1 | Promoted measured model is served (non-demo modes) | V2-01 | `reports/v2/holdout/` + served model manifest |
| 2 | H3 multi-holdout report exists | V2-01 | `reports/v2/holdout/h3_multiholdout.json` |
| 3 | No-Event / Rule-Event / LLM-Event separated | V2-03 | `reports/v2/llm_value/` |
| 4 | Predictive lift translated into profit/regret | V2-02 | `reports/v2/ledger/` |
| 5 | LLM incremental cost included | V2-03 | `reports/v2/llm_value/incremental_value.json` |
| 6 | GraphRAG correctness + relevance evaluated | V2-06 | `reports/v2/copilot/` |
| 7 | All UI metrics point to artifacts | V2-07 | UI results carry `run_id`/`artifact_id` |

## 5. Profit integrity

- Separate **contribution margin** from **shortage externality**; never merge them.
- Do not double-count lost margin with shortage cost.
- Cost and elasticity live in a **versioned assumption set** (`config/v2/`), not inline constants.
- The **Oracle** policy is an offline upper bound only — never presented as an achievable result.

## 6. Mandatory policies

```text
No Action · Greedy · Single-period MILP · MPC     (required, must be compared)
SP / CVaR                                          (optional)
RL / QAOA                                          (research-only — NOT a completion condition)
```

## 7. LLM boundaries

- LLM is used only for **event structuring, tool routing, and explanation**.
- LLM does **not** compute demand, price, or profit numbers directly.
- A numeric Copilot answer with **no typed tool result behind it is rejected**.

## 8. Claims taxonomy

Every API/UI result carries `run_id`, `artifact_id`, `mode`, `claim_status`, `freshness`.
Allowed `claim_status` values:

```text
measured · offline_benchmark · simulated · pending_live_label
assumption · blocked_data · blocked_external · demo_fixture · research
```

See `V2_CLAIMS_MATRIX.md` for the full envelope and the current (all-`pending`) matrix.

## 9. Invariants carried over from the base contract

Temporal correctness and `available_at <= forecast_cutoff` leakage rules; UTC storage +
`America/New_York` local aggregation; no random split for temporal forecasting; mode separation
(demo/replay/live/research); no fabricated metrics/news/citations; no causal claims from feature
attribution; no quantum-advantage claims; simulator ≠ hardware; v0/v1 contracts stay
backward-compatible unless a documented migration is part of a phase.
