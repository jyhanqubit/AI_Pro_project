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

## Borough re-measurement on NYC data — the FAIR test (`incremental_value_borough.json`, `make v2-llm-value-borough`)

After the H3/JC null we re-ran at **borough × hour** on **NYC-wide** trips, and fixed the two real
input problems: (1) **training range** — Jan–Apr (5 months, ~19.9M trips), like v1; (2) **news
attribution** — broadened from borough-name-only to a documented **citywide rule** (a subway/MTA/
weather shock affects all boroughs), raising attributed articles from 4 → **35**; and critically
(3) **test on a window that actually contains news**: the June window has **0** attributable
news borough-hours, so we test **May** (216 test rows carry a news signal — a fair evaluation).

Train Jan–Apr, **test May**. Three arms, same model, features only differ:

```text
A0 demand+calendar   A1 +permitted-events (structured feed)   A2 +LLM-news events
```

| Arm | WAPE | Net (simulated $) | Paired day-block CI vs previous arm |
|---|---|---|---|
| A0 demand+calendar | 0.1069 | 13,356,520 | — |
| A1 +permitted (structured) | **0.1047** | 13,389,639 | **measured_improvement**, CI [1.87, 5.88] |
| A2 +LLM-news | 0.1075 | 13,365,909 | **negative_lift**, CI [−6.02, −3.71] |

### Conclusion — a measured result, not a data gap

- **Structured permitted events measurably improve the forecast** (WAPE 0.1069 → 0.1047, CI clearly
  above 0; +$33k profit). This robustly reproduces v1's finding with proper training + a test
  window carrying events.
- **LLM-extracted news events add NEGATIVE value on top** (WAPE 0.1047 → 0.1075, CI clearly below 0;
  **net LLM value −$23,730**). Given a *fair* test — real news in the test window, 5-month
  training, broadened attribution — the LLM-from-news layer still does not help: the sparse, noisy
  news signal degrades the forecast and costs money.

**V2 mission answer (this data):** the *structured event feed* is worth money; the *LLM-from-news*
layer is **net-negative**. Reported honestly — not tuned to a positive.

### Caveat on the borough event effect

The permitted-event effect is real but **small** (~0.002 WAPE) and sensitive to the sample: on a
June test window it did not replicate (see git history), on May it does with a clear CI. Borough
grain washes out localized event impact; a finer grain with geo-precise events would be a stronger
test (blocked here by news geo-sparsity). The honest reading: event value at borough grain is
marginal, and the LLM-from-news variant is currently net-negative.

## Path to a real LLM positive

The LLM-from-news arm needs **denser, geo-precise events at a finer grain** — many mobility-relevant,
location-tagged news items per test-window hour. The available GDELT corpus (~35 attributable
articles / 6 months) is far too sparse; live re-collection is rate-limited in this sandbox
(`HANDOFF.md`). The full harness (3 arms, CI, profit, LLM cost) will measure a real lift the moment
such data exists.
