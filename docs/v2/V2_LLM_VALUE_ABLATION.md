# V2 LLM Incremental Value Ablation (V2-03)

The core V2 question: does the **LLM** event layer add value over a plain **rule** layer, after
its own cost? This requires cleanly separating three feature arms and reporting net-of-cost lift.

> **Status: implemented + run (V2-03). Honest null.** Runner `ml/forecasting/llm_value.py`
> (`make v2-llm-value`). On real JC Citi Bike 2026 H1 + real GDELT NYC 2026 news (371 articles),
> the three arms are **statistically identical** (ΔWAPE = 0, 95% CI [0,0]); event coverage on
> the test windows is 0.306% and `arms_identical_on_test = true`, so the verdict is
> **`insufficient_event_overlap`** (`claim_status: blocked_data`). LLM actual cost $0 (mock),
> estimated real $0.0061; **net LLM value −$0.01**. This rigorously confirms v1's gap with the
> full 3-arm + CI + profit + cost framework — a valid, honest outcome, not fabricated positive.
> Full result + unblock path: `reports/v2/llm_value/`.
>
> **Borough re-measurement (NYC) — the FAIR test (`make v2-llm-value-borough`).** Fixed the inputs:
> 5-month training (Jan–Apr, ~19.9M NYC trips), citywide news attribution (4→35 articles), and
> test on **May** (June's test window had 0 attributable news; May carries 216 news rows). Arms
> A0 / A1 (+permitted structured feed) / A2 (+LLM news). **Result:** A1−A0 =
> **measured_improvement** (WAPE 0.1069→0.1047, CI [1.87, 5.88], +$33k) — structured events help;
> A2−A1 = **negative_lift** (WAPE 0.1047→0.1075, CI [−6.02, −3.71], **net LLM value −$23,730**) —
> the LLM-from-news layer, even given a fair test, *degrades* the forecast and costs money.
> **V2 answer (this data): structured event feed = worth money; LLM-from-news = net-negative.**
> Caveat: the borough event effect is small (~0.002 WAPE) and sample-sensitive. Artifact:
> `reports/v2/llm_value/incremental_value_borough.json`.
>
> **Real-LLM extraction — decisive test.** To remove the "mock keyword extractor is bad" confound,
> claude-opus-4-8 (this session) read all 371 articles and produced a clean, grounded NYC event set
> (`data/fixtures/news_live/claude_events_2026h1.jsonl`, 23 events: LIRR strike, NYC flash floods,
> concerts/festivals, blizzard travel bans — off-topic/false-positive items rejected). Re-run
> (`make v2-llm-value-borough --claude-events ...`, test May, 336 clean news-signal rows): A1−A0
> **measured_improvement** (WAPE 0.0908→0.0883, CI [1.08,6.71]); A2−A1 **still negative_lift**
> (WAPE 0.0883→0.0905, CI [−5.32,−1.56], net LLM value −$17,789). **Even a real, high-quality LLM
> extraction does not make news events net-positive** over the dense structured permitted feed —
> news events are sparse, temporally coarse, and redundant with the official schedule. The negative
> is not an extraction-quality artifact.

## The decision metric — LLM Feature Value (LFV)

The paragraphs above report the A2−A1 comparison as prose + a CI. V2 also formalizes the question
*"did the LLM features meaningfully improve forecast accuracy?"* into **one decision-grade metric**
(`ml/forecasting/llm_feature_value.py`, emitted in the artifact as `llm_feature_value_metric`):

```text
skill = (WAPE_without_LLM − WAPE_with_LLM) / WAPE_without_LLM      # + = error reduced
```

- **Measured on the LLM-active subset**, not globally. LLM features are 0 on almost every zone-hour,
  so a global skill is diluted toward 0 and hides the effect. The subset is defined by the feature
  being *on* (never by the outcome), so it cannot cherry-pick favorable rows — this is the CLAUDE.md
  "event-window WAPE" principle applied to the LLM-active window.
- **Decision needs BOTH effect size and significance:** `MEANINGFUL_*` only when `|skill| ≥ 1%`
  (pre-declared `rel_threshold`) **and** the day-block bootstrap CI on the paired per-row abs-error
  gain excludes 0. Otherwise `NO_MEANINGFUL_EFFECT`; `< 100` active zone-hours ⇒ `INSUFFICIENT_SUPPORT`
  (`blocked_data`, no verdict faked). Same leakage-safe block bootstrap as the A2−A1 test.

| decision | meaning |
|---|---|
| `MEANINGFUL_POSITIVE` | LLM features cut error on active zone-hours, CI-significant |
| `MEANINGFUL_NEGATIVE` | LLM features raised error on active zone-hours, CI-significant |
| `NO_MEANINGFUL_EFFECT` | effect below threshold or CI covers 0 |
| `INSUFFICIENT_SUPPORT` | too few active zone-hours to decide |

> **Measured result (test May, Claude-extracted events, Jan–Apr train / 10,655 rows):**
> **`MEANINGFUL_NEGATIVE`** — on the **336** LLM-active zone-hours the LLM features **raise** WAPE by
> **5.52%** (skill −0.0552), bootstrap CI on the paired abs-error gain **[−17.51, −0.98] excludes 0**.
> Note the *global* A2−A1 mean gain (−3.53) is significant too, but the metric's active-subset focus
> makes the verdict sharper and undiluted (global skill only −2.5%). **So the quantified answer is:
> adding the LLM news features does NOT improve demand-forecast accuracy — it measurably degrades it
> where the features fire.** Consistent with the negative net LLM value (−$17,789). Artifact field:
> `incremental_value_borough.json#llm_feature_value_metric`.

The core is a pure function, unit-tested on synthetic positive/negative/null/insufficient cases
(`tests/unit/test_llm_feature_value.py`), so the decision logic is verifiable without the trip
pipeline.

## Three arms (identical cutoffs/splits)

```text
A0  No-Event    : demand history + calendar only
A1  Rule-Event  : A0 + deterministic rule-based event features
                  (keyword/geo/time rules — no LLM)
A2  LLM-Event   : A0 + LLM-extracted + graph-propagated event features
```

All three run on the **same** rolling H3 holdout windows (`V2_EVALUATION_PROTOCOL.md`) with the
same seed. Arms differ only in features.

## What is measured

```text
predictive lift : metric(A1) - metric(A0)     (rule value)
                  metric(A2) - metric(A1)     (LLM incremental value over rule)
profit lift     : net(A2) - net(A1)           (via the ledger, V2-02)
LLM cost        : tokens, $ per run, amortized per decision
net LLM value   : profit lift - LLM cost
```

Report lift with a confidence interval (e.g. block-bootstrap over holdout windows). Rule and LLM
arms must be attributable, not conflated.

## Honesty requirements

- If **A2 does not beat A1**, report it plainly and analyze why (event overlap, extraction
  quality, propagation). A null result is a valid, publishable V2 outcome.
- LLM incremental cost is **always** included — a lift that costs more than it earns is reported
  as net-negative.
- "Model-attributed" wording only; no causal claim.
- No fabricated event content to manufacture overlap (base-contract invariant).

## Artifact schema — `reports/v2/llm_value/incremental_value.json`

```jsonc
{
  "run_id": "run_...",
  "arms": {
    "A0_no_event":   { "wape": null, "net": null },
    "A1_rule_event": { "wape": null, "net": null },
    "A2_llm_event":  { "wape": null, "net": null }
  },
  "lift": {
    "rule_over_none":  { "wape_delta": null, "ci": [null, null] },
    "llm_over_rule":   { "wape_delta": null, "ci": [null, null] },
    "profit_llm_over_rule": null
  },
  "llm_cost": { "tokens": null, "usd": null, "usd_per_decision": null },
  "net_llm_value": null,
  "claim_status": "pending"
}
```

## Acceptance

- Three arms separated and reproducible from config.
- Shared cutoffs/splits verified.
- Cost included; net value reported; null results not hidden.
