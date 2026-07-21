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

### Feature improvement + graph contribution (`make`-able: `ml/forecasting/llm_graph_value.py`)

The −5.52% told us the *feature engineering* was the problem (flat 24h box anchored at publish time,
citywide smear). The improved builder (`ml/forecasting/event_features_v2.py`) fixes it: anchor to the
**event date + a type-specific peak hour**, shape with a **half-life decay** (peaked, not flat),
**gate by availability** (leakage-safe), **scope boroughs by type** (venue/gathering/safety = named
only; weather/transit/system may be citywide), bounded severity. A separate **graph** arm adds
neighbor spillover via borough-centroid distance decay. Arms A0 → A1(permitted) → A2(improved direct,
no graph) → A3(+graph); measured on real NYC demand (test May, 10,655-row train, 336→ split into 194
direct-active / 222 graph-active zone-hours):

| comparison | decision | active skill | CI95 |
|---|---|---|---|
| **improved LLM feature** (A2 − A1) | `NO_MEANINGFUL_EFFECT` | −0.4% | [−4.90, 1.36] |
| **graph contribution** (A3 − A2) | `NO_MEANINGFUL_EFFECT` | −1.32% | [−3.76, 0.72] |

**Honest reading:**
- The improvement **removed the harm**: the LLM feature went from `MEANINGFUL_NEGATIVE −5.52%` (old
  flat-box) to `NO_MEANINGFUL_EFFECT −0.4%` (CI now spans 0). Better feature engineering ⇒ no longer
  degrades the forecast — but it is now **neutral, not positive**.
- The **graph contribution is not proven** on this test: `NO_MEANINGFUL_EFFECT`, CI covers 0 (point
  estimate slightly negative). We do **not** claim the graph helps here.
- **Why borough grain handicaps the graph (a real caveat, not an excuse):** with only 5 boroughs the
  spatial-spillover mechanism the graph adds is coarse (centroids 8–20 km apart), and the dense
  structured permitted feed (A1, 2,600 active rows) already captures the real shocks. The graph's
  neighbor-propagation value is designed for **fine H3-zone grain** (hundreds of adjacent hexes),
  which is the fair venue for a graph-vs-no-graph claim. That test is not yet run.

Artifact: `reports/v2/llm_value/graph_contribution.json`.

### "News → permit-DB" reconstruction — hypothesis REFUTED (`ml/forecasting/llm_permitize_value.py`)

Hypothesis tested: the permit feed works because it is a precise structured DB (exact time + exact
borough, known in advance); so if the LLM re-extracts news into that **same permit schema**, the
structured version should help where raw news doesn't. I (in-session) rebuilt all 23 news events as
permit-quality records — precise `event_start_at`/`event_end_at` + specific borough inferred from the
article (`claude_events_permitized_2026h1.jsonl`) — availability-gated.

| arm | WAPE |
|---|---|
| A1 (permit feed) | 0.0883 |
| A2 news **raw** (coarse) | 0.0883 |
| A2 news **permitized** (precise time + borough) | **0.0940** |

| comparison | decision | active skill | CI95 |
|---|---|---|---|
| permitized − A1 | `MEANINGFUL_NEGATIVE` | **−6.31%** | [−25.2, −5.5] |
| permitized − raw news | `MEANINGFUL_NEGATIVE` | **−6.30%** | [−22.7, −5.8] |

**The hypothesis is refuted: giving news events permit-quality precision made the forecast *worse*,
not better — worse even than vague raw news.** Two honest mechanisms:

1. **Sparse + confident = confident noise.** Raw news features were vague and diffuse, so the tree
   mostly ignored them (≈0 effect). Permitized features are sharp and confident (weight 1.0 across a
   precise interval in a specific borough), so the tree *trusts* and adjusts on them — but the ~19
   news events' true demand effect is heterogeneous and unlearnable from so few examples (a transit
   strike may *raise* bike demand via substitution or *lower* it; a festival raises it locally), so
   the confident feature injects a wrong, high-variance adjustment. Precision amplifies the harm.
2. **The permit feed's value is density, not per-event structure.** A1 works because it carries
   **63,070** events — enough for the model to learn a stable "permitted-event → demand" coefficient.
   News supplies ~19. No amount of per-event precision fixes a sample that small.

3. **Timing gap (reported, not hidden):** 4 of 23 events were `leakage_dropped` — retrospective
   reviews whose show preceded publication, so they can't inform a forecast at all. Permits are filed
   in advance; news is coincident-or-after.

**Conclusion:** it is *not* the structure that the permit feed provides and news lacks — it is the
**volume and consistency** of events. Restructuring sparse news into a permit schema cannot recover
that, and here actively hurt. Honest negative result, not faked. Artifact:
`reports/v2/llm_value/permitize_contribution.json`.

### (a) News as an IMPORTANCE WEIGHT on the dense permit feed — also negative (`llm_importance_weight_value.py`)

Follow-up to the density finding: keep the dense permit signal (63,070 events) and let news only
*modulate* it — the permit features amplified by a news-importance scalar, untouched where there is
no news. The feature that enters the model:

```
news_salience[b,h] = news importance in the borough-hour (severity x half-life decay, gated); 0 if none
ev_active_newswt   = ev_active * (1 + news_salience)
ev_crowd_newswt    = ev_crowd  * (1 + news_salience)
```

Example values actually fed to the model (from the run):

| borough-hour | ev_active | news_salience | ev_active_newswt |
|---|---|---|---|
| Manhattan 2026-01-24 19 | 63 | 0.90 | **119.70** |
| Queens 2026-01-24 19 | 14 | 0.90 | 26.60 |
| *(any borough-hour with no news)* | k | 0.00 | k×1.0 = k (unchanged) |

| comparison | decision | active skill | CI95 |
|---|---|---|---|
| importance-weighted − A1 | `MEANINGFUL_NEGATIVE` | **−7.82%** | [−25.6, −5.9] (WAPE 0.0883→0.0925) |

**Also negative — and the example row shows exactly why.** The largest-salience cells are *Winter
Storm Fern* (2026-01-24, severity 0.9): the weight *amplifies* permit activity 63 → 119.7 because the
storm is "newsworthy". But a blizzard **suppresses** bike demand — so "newsworthy" points the wrong
way. News salience is a "something big is happening" signal whose *relationship to demand is
heterogeneous and often opposite* (storms depress, festivals lift), and ~191 rows across mixed types
is far too few to learn the sign per type. So even as a gentle multiplier, news injects a
confident, wrong-signed adjustment.

### (b) H3-grain graph contribution — blocked (no geocoded events)

The fairest venue for the graph (fine H3 zones with neighbor propagation) **cannot be run on the real
data**: `pipelines/features/graph_features.py` places events on H3 zones by `lat/lng`, but the real
permit and news events are **borough-tagged only** (permits also carry a street *description* +
precinct number, but no coordinates). Geocoding street/precinct text needs external data not present
offline, and fabricating coordinates is not allowed. So the **borough-grain graph test above (null)
is the finest fair test the real event data supports.** Recorded as `blocked_data`, not forced.

### SIGNED LLM demand signal — direction from the LLM (`llm_signed_value.py`)

The importance-weight failure was that it was *unsigned* (always amplify), so a blizzard pushed the
forecast up. The fix: have the LLM emit a **signed** `demand_effect ∈ [−1,+1]` per event (blizzard
−0.9, festival +0.5, LIRR shutdown **+0.6** via bike substitution) and build a signed feature
`news_demand_signal = demand_effect × severity × decay`. The model gets the direction *from the LLM's
reasoning* rather than learning it from ~19 sparse events (`claude_events_signed_2026h1.jsonl`).

| | value |
|---|---|
| **LLM sign-correctness** (agrees with actual demand deviation vs same-hour-last-week, 191 cells) | **0.77** |
| WAPE: A1 → +signed | 0.0883 → 0.0906 |
| signed − A1 | **`NO_MEANINGFUL_EFFECT`** −2.04%, CI [−7.26, +1.44] |

**This is the key result. The LLM's direction is genuinely correct (0.77 agreement) — fixing the
sign turned the −7.82% *harm* into a −2.04% *neutral* — yet it still does not improve the forecast.**
The reason is redundancy: when a blizzard is suppressing demand, the autoregressive features
(`dep_lag_1`, `dep_lag_24`, `dep_roll_mean_24`) **already show demand is low** — the model *already
sees* the effect. A signed news signal that says "demand is down now" is largely **redundant with the
demand history** for ongoing events. News could only add value at the *sudden onset* of an
unanticipated shock (before the lags catch up) — rare, and blunted here by coarse timing + the
availability gate.

### Post-processing correction with per-mechanism factors — also negative (`llm_postprocess_value.py`)

Practitioners often correct a forecast *after* the model rather than as an input. So instead of a
feature, apply `pred_corrected = pred_base + Σ_channel α_channel · signal_channel`, with a **separate
factor per mechanism** (n-dimensional context: weather / gather / transit / safety) **calibrated on
the train residuals and applied out-of-sample to test**.

| calibrated factor (fit on train) | value |
|---|---|
| α[weather] | +20.3 |
| α[gather] | **−470.6** |
| α[transit] | **−477.8** |
| α[safety] | +155.9 |

| | WAPE | verdict |
|---|---|---|
| A1 base | 0.0883 | — |
| A1 post-processed | 0.0899 | `MEANINGFUL_NEGATIVE` −21.36%, CI [−102.6, −4.95] |

**Also negative — and the fitted factors show why.** The magnitudes are **absurd** (−470, −477) and
`gather`/`transit` have the **wrong sign** (a positive surge signal multiplied into a huge *negative*
correction). That is textbook **overfitting the calibration**: least-squares fit large coefficients
to the handful of dev event-cells (746, dominated by a few events) that fit dev noise and fail on
test's *different* events. The sparsity problem simply moved from "the tree can't learn a coefficient"
to "the post-processing calibration can't either". A fixed (unfitted) factor equals the signed-feature
arm — neutral. Either way, ~19 events cannot pin down a stable event→demand factor.

### Forecast-horizon sweep — the "redundancy" rescue also fails (`llm_horizon_value.py`)

The redundancy explanation implied a way out: at a longer horizon the recent lags are unavailable, so
forward-looking event knowledge should matter more. Tested by refitting with only horizon-legal
features (lag_k usable iff k≥h; no rolling/momentum for h>1):

| horizon | WAPE A0 → A1 → A2 | permit (A1−A0) | news (A2−A1) |
|---|---|---|---|
| 1h (nowcast) | 0.0908 → 0.0883 → 0.0906 | **+2.69% MEANINGFUL_POSITIVE** | −2.04% neutral |
| 6h / 24h | 0.1826 → 0.1824 → 0.1808 | −0.0% neutral | −9.59% neutral |
| 48h | 0.2187 → 0.2162 → 0.2145 | +1.09% neutral | −2.82% neutral |

**Not supported.** Event value does *not* grow with horizon. Dropping the recent lags roughly
*doubles* the baseline WAPE (0.09→0.18→0.22), which widens the noise and **weakens** the permit
signal's significance (it is `MEANINGFUL_POSITIVE` only at nowcast) instead of strengthening it.
News stays neutral-to-negative at every horizon. So the null is not a nowcasting artifact that longer
horizons would fix.

### Overall V2-03 finding (consistent across every attempt)

Six attempts — improve extraction, add graph propagation, reconstruct into permit schema, reweight
the permit feed by news importance, a **signed** LLM demand direction, and a **post-processing**
correction with per-mechanism factors — are **all neutral-to-negative.** The story tightened at each
step:

1. Raw / improved news feature → neutral-to-negative (coarse, sparse).
2. Permit-schema reconstruction → negative (sparse + confident = confident noise).
3. Unsigned importance weight → negative (blizzard amplified demand the *wrong way*).
4. **Signed** demand direction → the LLM's sign is **77% correct**, harm removed, but **still no
   improvement** — because the autoregressive demand history already encodes the effect of an ongoing
   event; the news signal is **redundant** with the lags.
5. **Post-processing** correction (per-mechanism factors, calibrated on train) → negative; the fitted
   factors are absurd/wrong-signed (−470) — the sparse calibration **overfits** and fails on test.

6. **Horizon sweep** → event value does not grow with lead time; the null is not a nowcasting artifact.

**Conclusion:** LLM-from-news does not improve demand forecasting on this data, and we
now understand *why* at three levels — (a) **sparsity** (~19 events can't teach a magnitude/factor,
whether a model coefficient or a post-processing calibration), (b) **sign heterogeneity** (fixed by a
signed LLM effect, which is 77% right), and (c) **redundancy** with the autoregressive demand history
(and it is not rescued at longer horizons). News would only help at the sudden onset of an
*unanticipated* shock before the lags react — rare, and limited here by coarse timing and the
availability gate. This is a negative result understood, not merely observed.

### Is it really sparsity? Density learning curve + quality ablation (`llm_density_curve.py`, `llm_quality_ablation.py`)

"Sparsity" was asserted, not proven — and news differs from permits on three confounded axes
(density, precision, forward timing). Two controlled ablations isolate the cause.

**Density curve** — subsample the dense permit feed to news-scale counts, holding precision + timing
at permit quality:

| N permit events | permit A1−A0 |
|---|---|
| 20 / 50 / 100 | INSUFFICIENT / neutral / neutral |
| 300 | **+2.03% MEANINGFUL_POSITIVE** |
| 1000 / 3000 / 10000 | neutral (non-monotonic) |
| 63,070 (all) | **+2.69% MEANINGFUL_POSITIVE** |

Two facts: (1) at **news scale (≤100 events; news has ~19) there is no value** → density is
*necessary*, and 19 is structurally in the dead zone. (2) the curve is **non-monotonic** (value at
300, gone at 1000–10000 on a single random subsample, back at full) → raw count is *not sufficient*;
**which** events you have matters — diluting with low-relevance permits washes out the count feature.
So "just collect more news" would not reliably fix it: you need enough *demand-relevant* events, not
just more rows.

**Quality ablation** — hold density at FULL and degrade one axis to news-like:

| mode | what's degraded | permit A1−A0 |
|---|---|---|
| **full** | nothing (control) | **+2.69% MEANINGFUL_POSITIVE** |
| coarse_time | exact hour → flat over the day | **−0.33% collapses** |
| citywide | exact borough → all boroughs | **+0.53% collapses** |
| retro | advance → known only after onset | **+1.01% collapses** |

**Every single quality degradation collapses the value to non-significant.** So precise time, precise
location, and forward-looking timing are each *necessary* — remove any one and the permit feed stops
helping.

**The proven cause is a conjunction of four properties, not a lazy "sparsity":** the permit feed works
because it is (1) **dense** (≥ a few hundred demand-relevant events), (2) **precisely timed** (exact
hour), (3) **precisely located** (exact borough), and (4) **forward-looking** (known before the
event). News fails on **all four**: ~19 events (below the density threshold), day-and-borough-level
coarse (fails time + location), and retrospective (fails timing). Critically, **"collect more news"
only addresses axis (1); news would still fail on (2)–(4), because coarse, after-the-fact reporting is
what news structurally *is*.** That is the real answer — the null is over-determined by structural
properties of news, and cannot be fixed by volume alone.

### Can news even *satisfy* the four conditions? (`news_condition_audit.py`)

A tempting next step: "encode a 4-D feature vector so news meets the four conditions." But the
conditions are properties of the **source** (what information exists), not of the encoding — an
extractor cannot invent an unstated hour or make a retrospective review forward-looking. Auditing the
23 events against the two source-checkable axes:

| condition | news events satisfying |
|---|---|
| forward-looking (published >3h before onset) | **2 / 23** |
| precise single-borough | 12 / 23 |
| **BOTH forward AND precise** | **1 / 23** (and it is June — outside the May test window) |

The qualifying subset is **~empty (1/23)**, because 21/23 news items are **coincident-or-retrospective**
(lead time ≤ 0 — news reports events *as/after* they happen; density is ~19 besides). A 4-D vector or
reliability-weighted post-correction is sound *in principle*, but with a 1/23 reliable subset it
reduces to nothing. This is not fixable by encoding or by more volume: forward-looking, precise events
come from **schedules / permits / announcements**, not from retrospective news. The honest path to an
LLM demand contribution is therefore to have the LLM structure a **forward-looking event source** into
the A1 slot — which, when it exists (the permit feed), already delivers +2.69% / +$33k.

### Synthetic ceiling — the post-correction DOES work when conditions are met (`llm_synthetic_ceiling.py`, `claim_status: simulated`)

To prove the post-correction is *capable* (not to claim real-news value), a disclosed simulation:
inject KNOWN forward-looking, precise, dense event shocks (surge ×1.3–1.7 / suppress ×0.5–0.8) into
real demand; the "LLM" signal knows only sign + coarse magnitude; the correction factor α is fit on
train and applied to test. **This is `simulated`/`research`, fully disclosed — NOT a real-news result
and no business claim.**

| synthetic source | WAPE base → +feature → +post-corr | feature vs base | post-correction vs base |
|---|---|---|---|
| **dense + forward + precise** (1372 event-cells) | 0.1106 → 0.1042 → 0.1081 | **+20.86% MEANINGFUL_POS** | **+10.43% MEANINGFUL_POS** (CI [17.6, 108.7]) |
| sparse (news-scale, 157 cells) | 0.0953 → 0.0958 → 0.0956 | INSUFFICIENT_SUPPORT | INSUFFICIENT_SUPPORT |

**Two honest conclusions:**
1. **The LLM post-correction genuinely improves the forecast (+10.43%, CI excludes 0) — when the
   event source is dense + precise + forward-looking.** So the real-news null is a **source** problem
   (news fails the four conditions), *not* a pipeline/method limitation. The method is sound.
2. **At news-scale density even *perfect* events give nothing** (INSUFFICIENT_SUPPORT) — reconfirming
   density is necessary, from the mechanism side.

This closes the loop with the ablations: violate the conditions (real news) → no value; satisfy them
(this simulation, and the real permit feed at +2.69%) → value. The honest real-world path to an LLM
*demand* contribution is to have the LLM structure a genuinely forward-looking source (event
calendars / schedules / permits) into the A1 slot — not to squeeze it from retrospective news.

### LLM structuring the real permit feed — priors HURT, facts should be learned (`llm_permit_enrich_value.py`)

The chosen path (A): the permit feed already satisfies the four conditions, so give the LLM its job —
read each permit's free-text type/name and enrich the crude count. **Attempt 1 imposed the LLM's
demand DIRECTION** (parade +0.4, film/production −0.3, market +0.2) as a signed feature:

| arm | WAPE |
|---|---|
| A0 | 0.0908 |
| A1 crude counts | **0.0883** (+2.69% vs A0) |
| A1 + LLM signed enrichment | **0.0914** (−3.39% vs crude, MEANINGFUL_NEGATIVE) |

**It hurt — worse than A0.** The lesson confirms the V2 contract's own rule ("the LLM does not
directly compute demand"): the crude count works *because* it is agnostic — the tree **learns** each
situation's demand response from data. Imposing an **unvalidated demand-direction prior** overrides
that with a guess that, when wrong, actively misleads.

**Attempt 2 fixed that** — LLM structures FACTS only (categorize `event_type` into 6 buckets:
surge / gather / openstreet / market / production / civic), NO sign imposed, model learns each
bucket's response:

| arm | WAPE | vs crude |
|---|---|---|
| A1 crude counts | 0.0883 | — |
| A1 + per-type buckets | 0.0899 | **−1.9% MEANINGFUL_NEGATIVE** |

**Also negative.** Disaggregating one count into six sparser bucket-counts gives the model 6
coefficients to fit on the same ~2,600 event-active cells → it overfits; the low-variance aggregate
count already captures the usable "how much permit activity" signal. Any per-type demand differences
are too small/noisy to recover at borough-hour grain with this many events.

**Finding for path (A):** on this real forward-looking source, LLM *semantic structuring* beyond a
simple aggregate count does not help — neither imposing direction (−3.39%) nor factual type-splitting
(−1.9%). **The aggregate event count is the ceiling on this data/grain.** Finer LLM structure would
need a finer spatial grain (per-H3-zone, where a parade route localizes) — blocked here because the
permits are borough-tagged (no coordinates). This is exhaustive for the demand side; further demand
experiments would be fishing.

### "How can more information reduce accuracy?" — train vs test diagnostic (`llm_overfit_diagnostic.py`)

The intuition is correct: for an ideal learner, more features can never hurt. The train-vs-test
breakdown shows what actually happens (and corrected our first hypothesis — it is **not** classic
overfitting):

| arm | #feat | TRAIN WAPE | TEST WAPE |
|---|---|---|---|
| A0 demand+calendar | 32 | 0.0631 | 0.0908 |
| A1 crude aggregate count | 36 | **0.0485** | **0.0883** |
| A1 typed (6 buckets) | 40 | 0.0533 | 0.0899 |

Two readings:
1. **More information genuinely helps** — A1 crude beats A0 on **both** train (0.0485<0.0631) and test
   (0.0883<0.0908). Adding the permit signal improves fit *and* generalization, exactly as intuition
   says.
2. **Typed is worse than crude on both train AND test** — so it is not overfitting (that would be
   better train, worse test). It is **representation dilution**: the six per-type buckets carry the
   *same* information as the aggregate count (their sum ≈ the count), but each bucket is ≈0 in most
   active cells. A capacity-limited greedy boosted tree (fixed leaves/iterations, early stopping)
   exploits **one dense high-signal feature** better than six sparse ones — splits on sparse columns
   are low-value and waste the budget, so even the training fit degrades.

**So "more information" never reduced accuracy — the *same* information in a sparser encoding did.**
An infinite-data / infinite-capacity model would tie (the typed set contains the count as a sum); the
loss is finite-sample representation efficiency. The practical lesson is a feature-engineering one:
the aggregate count is the better *encoding*, and finer LLM structure only pays off with enough
per-type event density (or a finer spatial grain) to estimate each slice — which this data lacks.

> **Synthesis:** the "where and why LLM features matter" summary is in
> [`V2_WHY_LLM_FEATURES.md`](V2_WHY_LLM_FEATURES.md).

### Insight — where the LLM adds value, and how to attribute the WAPE lift

The demand-feature avenue for **news** is exhausted — but that was never the whole thesis. Two
LLM/event contributions are **measured positives** in V2:

1. **The structured event layer improves the forecast.** The permit feed adds
   `MEANINGFUL_POSITIVE +2.69%` at nowcast (A1−A0) and **+$33k** in the ledger — the core
   "event-aware forecasting" claim, measured. The pipeline is *event-source agnostic*: a
   forward-looking, dense, geocoded LLM event stream would enter exactly the same A1 slot. NYC's
   retrospective/sparse GDELT news simply is not that stream.
2. **The LLM adds measured value in structuring, routing, and explanation** — V2-06: the real-LLM
   Copilot router scores 1.0/1.0/1.0 vs a keyword baseline's 0.75, cutting hallucinated answers 3→0.
   This is where the addendum always placed the LLM ("event structuring, tool routing, explanation;
   the LLM does not directly compute demand").

So the V2 verdict is not "the LLM is useless" — it is: **the LLM's verified value is in
structuring/routing/explanation and in powering the event layer, not in extracting extra demand
accuracy from sparse retrospective news.**

**Attribution guardrail (for the portfolio).** The measured WAPE lift belongs to the **structured
event feed**, not to the LLM. The repo already states this correctly — the headline lift
(`borough_event_lift.json`, WAPE −1.65% / V2 A1−A0 +2.69%) is labeled *event-feature* lift and comes
from the NYC permit feed (no LLM), and the B0–B4 ablation shows **B3 (+LLM event features) = B1** (no
lift). So any claim of the form "LLM features improved WAPE" is **not supported** and should read:

> *Structured event features improved WAPE (measured); LLM-from-news added no incremental forecast
> lift (verified across 7 approaches). The LLM's measured value is in GraphRAG grounding / routing /
> explanation (answer correctness 40%→100%, hallucinations 10/10→0), not in demand accuracy.*

The remaining unrealized demand niche for the LLM is a source that is **unstructured *and*
forward-looking** — event previews / press releases / venue announcements / community notices — which
the LLM would structure into permit-quality records for the A1 slot. Retrospective GDELT news is not
that source (2/23 forward-looking), so this niche is recorded as untested (`blocked_data`), not
claimed.

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
