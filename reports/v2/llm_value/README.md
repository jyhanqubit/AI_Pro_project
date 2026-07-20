# reports/v2/llm_value/ — V2-03 LLM Incremental Value

**Run 2026-07-20.** Reproduce: `make v2-llm-value` (needs `data/raw/citibike_2026/` +
`data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl`; promoted model from `make v2-holdout`).
Schema/rules in `docs/v2/V2_LLM_VALUE_ABLATION.md`.

Artifact: `incremental_value.json` (result envelope). Three arms share cutoffs/splits and the
promoted model; **only the features differ**:

```text
A0 No-Event    = B1  demand + calendar
A1 Rule-Event  = B2  A0 + raw article-count features (no structured extraction)
A2 LLM-Event   = B4  A0 + LLM-extracted event features + graph-propagated features
```

## Result — honest null: `insufficient_event_overlap` (`claim_status: blocked_data`)

Real JC Citi Bike 2026 H1 (114,885 zone-hour test decisions) + real GDELT NYC 2026 news
(371 articles, mock extractor):

| Arm | WAPE | Event-window WAPE | Net profit (simulated) |
|---|---|---|---|
| A0 No-Event | 0.5030 | n/a | 228,992 |
| A1 Rule-Event | 0.5030 | n/a | 228,992 |
| A2 LLM-Event | 0.5030 | n/a | 228,992 |

| Incremental lift (ΔWAPE, <0 = better) | Point | 95% block-bootstrap CI | Verdict |
|---|---|---|---|
| A1 − A0 (rule value) | +0.0000 | [0.0000, 0.0000] | no_measurable_lift |
| A2 − A1 (**LLM value**) | +0.0000 | [0.0000, 0.0000] | no_measurable_lift |
| A2 − A0 | +0.0000 | [0.0000, 0.0000] | no_measurable_lift |

- **`arms_identical_on_test = true`**: the extracted events carried no signal into the test
  windows. Event coverage on test is **0.306%** (352 rows), and those rows are low-demand
  zone-hours — the real, geo-matched overlapping event volume is negligible on this JC/2026 slice.
- **LLM cost:** actual **$0** (offline mock); estimated real **$0.0061** (371 articles, assumption
  price). **Net LLM value (simulated): −$0.01** — the LLM adds cost without measurable benefit here.

This is the **same gap v1 flagged** (`insufficient_event_overlap`), now shown rigorously with the
full 3-arm + block-bootstrap-CI + profit + cost framework. It is a valid, honest V2 outcome —
not fabricated into a positive.

## Path to unblock a real positive measurement

Trip + news of the **same geography and period at sufficient event density** — e.g. NYC-wide
trips + NYC news (memory-bounded grain), or JC-specific event collection whose events geo-map to
JC H3 zones and overlap the trip window. The harness will then measure a real lift (or a real
null) with the CI + net-of-cost already in place.
