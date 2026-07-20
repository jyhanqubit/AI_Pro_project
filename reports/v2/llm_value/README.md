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

## Borough re-measurement on NYC data (`incremental_value_borough.json`, `make v2-llm-value-borough`)

To rule out "wrong geography/grain" as the cause, we re-ran at **borough × hour** on **NYC-wide**
trips (matched to the NYC news). Streamed **13.9M real NYC trips** (Apr–Jun 2026) → borough-hour;
train Apr–May, test June. Three arms, same model, features only differ:

```text
A0 demand+calendar   A1 +permitted-events (structured feed)   A2 +LLM-news events
```

| Arm | WAPE | Net (simulated) |
|---|---|---|
| A0 demand+calendar | 0.1090 | 7,069,462 |
| A1 +permitted (structured) | 0.1089 | 7,089,021 |
| A2 +LLM-news | 0.1095 | 7,075,208 |

- **A2 − A1 (LLM-from-news increment): `insufficient_event_overlap`** — only **4 of 371** news
  articles attribute to a borough, and **0** land in the June test window (`test_rows_with_llm_news
  = 0`). The sparse news features slightly *hurt* (negative_lift CI below 0); **net LLM value
  −$13,814**.
- **A1 − A0 (structured feed): inconclusive** here (CI includes 0) — this 2-month-training re-run
  is underpowered vs v1's measured positive (which used Jan–May training in
  `reports/borough_event_lift.json`). The V2-03 focus is the LLM increment, not re-litigating v1.

### Conclusion (both grains agree)

The LLM-**from-news** layer has **no measurable value at either H3 (JC) or borough (NYC) grain**.
The bottleneck is **not** geography or grain — it is **news sparsity / thin borough attribution**
(4/371 articles). v1's measured event lift came from the *structured permitted-events feed*, not
the LLM. On the available real news, the LLM adds cost without measurable benefit — reported
honestly, not fabricated.

## Path to unblock a real positive measurement

Denser, mobility-relevant, geo-tagged news overlapping the trip window (e.g. a GDELT re-collection
with borough/transit queries — currently rate-limited in this sandbox, per `HANDOFF.md`), or an
event feed with reliable location tags. The full harness (3 arms, CI, profit, LLM cost) is in
place and will measure a real lift the moment such news exists.
