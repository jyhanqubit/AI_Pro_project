# Project Status

_Last updated: 2026-07-20_

## V2 kickoff — LLM net-business-value verification (scaffolding)

V2 has been scaffolded on branch `claude/upgrade-v1-to-v2-fsn80p`: docs and folders only, **no
measured V2 results yet**. The V2 contract is `CLAUDE_V2_APPEND_REVISED.md` (imported by
`CLAUDE.md`); the plan lives in `docs/v2/` (start at `docs/v2/README.md`). V2 verifies — with
versioned artifacts under `reports/v2/**` — whether LLM/event features add measurable predictive
lift and whether that lift converts to profit net of LLM cost.

- **New docs:** `docs/v2/{README,V2_MISSION,V2_EXECUTION_PLAN,V2_CLAIMS_MATRIX,V2_EVALUATION_PROTOCOL,V2_PROFIT_REGRET_LEDGER,V2_LLM_VALUE_ABLATION,V2_MPC_DECISIONING,V2_PRICING,V2_GRAPHRAG_COPILOT,V2_KNOWN_LIMITATIONS}.md`.
- **New folders:** `contracts/v2/`, `config/v2/`, `data/fixtures/v2/`, `reports/v2/{holdout,ledger,llm_value,mpc,pricing,copilot,final}/`.
- **Phases:** V2-00…V2-06 **PASSED**; V2-07 … V2-09 `PLANNED` (see `docs/v2/V2_EXECUTION_PLAN.md`).
- **V2-06 done:** GraphRAG typed-tool Copilot (`ml/copilot/`, `make v2-copilot`). Numbers come only
  from typed tools reading committed V2 artifacts (with `artifact_id`); unanswerable questions are
  refused. **Two routers compared on 20 Q** — keyword matcher vs **real in-session claude-opus-4-8
  routing** (no API key; `copilot_routing_claude.jsonl`). claude: routing/correctness/refusal 1.0,
  hallucinated=0 (gates pass). keyword: hallucinated=3 (real-but-wrong-question numbers on decoys),
  gate FAIL. **Finding:** grounding (ungrounded=0) is structural for both, but refusing the wrong/
  unanswerable question needs the LLM — that's its measured value here. 8 tests. Artifact:
  `reports/v2/copilot/correctness_benchmark.json`.
  **GraphRAG half at scale** (`ml/copilot/graphrag_scale.py`): the 2-event figure was only the
  golden-path demo fixture — the real graph (`make seed-graph`) has **2,895 events / 6 zones /
  2,808 edges**. On 21 as-of questions, vs a FAIR flat-retrieval baseline (top-3 type-matched,
  zone-agnostic): flat **6/21** (grounds, refuses all 6 OOS, 0 halluc — not a strawman) vs GraphRAG
  **21/21**. **Honest caveat:** the task is graph-structural (gold = graph edges) so GraphRAG is
  high BY CONSTRUCTION — not a fair GraphRAG-vs-RAG bakeoff; a borough-tag filter would tie. Read
  as 'the Event→Zone edge is what makes per-zone queries answerable'. Artifact + caveats:
  `reports/v2/copilot/graphrag_benchmark.json`.
  **Neutral counterpart** (`ml/copilot/neutral_retrieval.py`): because the structural task can't let
  the graph lose, we also ran the mirror — a text lookup (paraphrase→event, 12 Q with
  method-independent gold). `flat_text` **0.833** top1 beats `graph_boosted` **0.750** (graph −0.083,
  no lift; degree boost distracts). Together the pair bounds the honest verdict both ways: graph wins
  relational/per-zone queries, plain text wins text lookup — match the tool to the query type.
  Artifact: `reports/v2/copilot/neutral_retrieval_benchmark.json`.
  **RAGAS cross-check** (`ml/copilot/ragas_retrieval.py`, real ragas 0.4.3 non-LLM retrieval metrics,
  top-10): ctx-precision flat_text **0.833** vs graph_boosted **0.771** (−0.0625), recall tied —
  a standard tool agrees the graph gives no retrieval lift. RAGAS generation-side metrics
  (faithfulness/answer_relevancy) need an LLM judge → `blocked_external` (no key), never faked.
  Optional dep `pip install -e '.[ragas]'`; absent ⇒ runner writes blocked_external.
  Artifact: `reports/v2/copilot/ragas_retrieval_benchmark.json`.
  **RAGAS generation-side** (`ml/copilot/ragas_generation.py`): faithfulness/answer_relevancy need an
  LLM judge → judged **in-session** (no key; verdicts committed to
  `data/fixtures/v2/copilot_ragas_judgments.jsonl`). 10 answered Q: **faithfulness 1.0**,
  **answer_relevancy 0.985**. Faithfulness is 1.0 by design (answers only restate tool values); the
  judging caught + fixed a real mislabel — `llm_news_value` stamped a simulated dollar figure as
  `measured` (→ `simulated`; q08 was 3/4=0.75 before). Drift guard fails the run if a judged answer
  drifts from the live Copilot; self-judgment recorded as caveat.
  Artifact: `reports/v2/copilot/ragas_generation_benchmark.json`.
- **V2-05 done:** bounded dynamic pricing `ml/pricing/pricing_v2_eval.py` + `pricing_v2_run.py`
  (`make v2-pricing`). Elasticity from the versioned assumption set, ledger objective, bounds/safety
  from `config/pricing_v2.py`. 576 seeded zone-hours: **0 guardrail violations**, safety zones
  base-fare, credit budget 0/40 respected, **negative control** catches a planted out-of-bounds
  surge; sensitivity grid (elasticity × surge-bound); **A/A switchback** effect ≈ 0 / CI covers 0
  (design valid). All `simulated` (shadow quotes, no rider charged, no causal claim). 7 tests.
  Artifacts: `reports/v2/pricing/{guardrail_audit,sensitivity}.json`.
- **V2-04 done:** multi-period MPC `optimization/mpc.py` + `mpc_run.py` (`make v2-mpc`). Four
  mandatory policies + Oracle on a seeded commute scenario, V2-02 ledger objective. Ledger cost
  (lower better): NoAction 1127 / Greedy 1155 / MILP 1087 / **MPC 740** / Oracle 719. **MPC is the
  best feasible policy** (regret 21.6 vs Oracle, ~3%), halves shortage+overflow vs single-period;
  Greedy net-harmful (reposition > imbalance relieved). MPC forecast-only (no leakage); Oracle
  offline bound (regret ≥ 0); all feasibility-checked. Dollars `simulated`. 7 tests. Artifact:
  `reports/v2/mpc/policy_comparison.json`.
- **V2-00 done:** result envelope `contracts/v2/{enums,envelope}.py` (`ClaimStatus` 9-value +
  `ResultEnvelope`, honesty rules enforced in code, 22 tests green); `make v2-audit` gate
  (domain-drift + contract check, exit 0); audit report `reports/v2/final/v2_audit.md`.
  Findings: 0 domain drift; JC-vs-NYC data nuance recorded; test-count inconsistency and legacy
  `v2-*` phase-number collision flagged for cleanup.
- **V2-01 done (measured):** `ml/forecasting/h3_multiholdout.py` (`make v2-holdout`) +
  `promoted.py` serving loader. Real JC Citi Bike Mar–Aug 2024, **210,042** H3 zone×hour rows /
  **234** zones, 3 rolling monthly windows. Promoted `hist_gradient_boosting`; aggregate
  **WAPE 0.4828 ± 0.0030, MASE 0.7996** (beats B0 seasonal-naive ~0.648 every window).
  Artifacts: `reports/v2/holdout/{h3_multiholdout,promoted_model}.json`. 5 leakage/window tests.
  Scope: JC slice, B1 features only (events = V2-03), promotion pool bounded, API wiring = V2-07.
- **V2-02 done:** profit/regret ledger `optimization/ledger.py` + `ledger_run.py` (`make v2-ledger`)
  + typed `contracts/v2/ledger.py` + versioned `config/v2/assumptions.yaml`. Over 114,079 zone-hour
  decisions the V2-01 forecast nets **+$103,271** vs seasonal-naive (sign robust across all 9 cost
  settings), regret vs Oracle **$218,697**. Unit counts measured; dollars `simulated` (assumptions
  not yet sourced). 8 tests (no-double-count, Oracle upper-bound). Relocation deferred to V2-04.
  Artifact: `reports/v2/ledger/profit_regret.json`.
- **V2-03 done (honest null):** `ml/forecasting/llm_value.py` (`make v2-llm-value`) — 3 arms
  (No-Event/Rule-Event/LLM-Event = B1/B2/B4), shared promoted model + splits, block-bootstrap CI,
  ledger profit, LLM cost model. Real JC 2026 H1 + real GDELT NYC 2026 news (371 articles). Arms
  **identical** (ΔWAPE=0, CI[0,0]), event coverage 0.3% → verdict **`insufficient_event_overlap`**
  (`blocked_data`); LLM actual $0 (mock)/est real $0.0061, **net LLM value −$0.01**. Rigorously
  confirms v1's gap; framework (arms/CI/cost) in place. 6 tests. Artifact:
  `reports/v2/llm_value/incremental_value.json`. Unblock path documented in the report.
  **Borough re-measurement — FAIR test** (`make v2-llm-value-borough`, 19.9M real NYC trips,
  borough×hour, 5-mo train Jan–Apr, test May with 216 news rows, citywide attribution 4→35):
  **A1−A0 (permitted, structured) = measured_improvement** (WAPE 0.1069→0.1047, CI [1.87,5.88],
  +$33k — reproduces v1 robustly); **A2−A1 (LLM-news) = negative_lift** (WAPE 0.1047→0.1075,
  CI [−6.02,−3.71], **net LLM value −$23,730**). **V2 answer (this data): structured event feed
  is worth money; LLM-from-news is net-negative** even given a fair test. Caveat: borough event
  effect small (~0.002 WAPE) & sample-sensitive. Artifact: `incremental_value_borough.json`.
  **Real-LLM extraction (decisive):** no API key in sandbox, so claude-opus-4-8 (this session)
  hand-extracted 23 clean NYC events (`data/fixtures/news_live/claude_events_2026h1.jsonl`,
  `--claude-events` path). Re-run test May, 336 clean news rows: A1−A0 measured_improvement
  (0.0908→0.0883); **A2−A1 still negative_lift** (0.0883→0.0905, CI [−5.32,−1.56], net LLM value
  −$17,789). LLM-from-news is net-negative **even with a real high-quality extraction** (news
  sparse/coarse/redundant vs the structured feed) — not a mock artifact. 6 tests.
- **V2-03 LLM Feature Value metric** (`ml/forecasting/llm_feature_value.py`): formalizes "did the LLM
  features meaningfully improve accuracy?" into one decision. Score = relative WAPE reduction on the
  **LLM-active subset** (not diluted globally) + day-block bootstrap CI; `MEANINGFUL_*` only when
  |skill|≥1% AND CI excludes 0, else `NO_MEANINGFUL_EFFECT`/`INSUFFICIENT_SUPPORT` (no faked verdict).
  Measured (test May, Jan–Apr train 10,655 rows, 336 active): **`MEANINGFUL_NEGATIVE`, active skill
  −5.52%, CI [−17.51,−0.98]** → LLM features measurably degrade accuracy where they fire. Emitted in
  the artifact as `llm_feature_value_metric`; pure fn with 6 synthetic unit tests
  (`tests/unit/test_llm_feature_value.py`).
- **V2-03 feature improvement + graph contribution** (`ml/forecasting/event_features_v2.py` +
  `llm_graph_value.py`): fixed the feature engineering (event-time anchor + half-life decay +
  type-scoped boroughs, replacing the flat-24h-from-publish box) and added a graph neighbor-spillover
  arm. Measured on real NYC demand (test May): **improved feature A2−A1 = `NO_MEANINGFUL_EFFECT`
  −0.4%** (CI [−4.90,1.36]) — the harm is **removed** (was −5.52%), now neutral not positive.
  **Graph A3−A2 = `NO_MEANINGFUL_EFFECT` −1.32%** (CI [−3.76,0.72]) — graph **not proven** at borough
  grain (only 5 coarse zones; structured feed already dense). Fair venue for the graph claim is
  H3-zone grain (existing `pipelines/features/graph_features.py`), not yet run. Honest null, not faked.
  6 pure-builder unit tests. Artifact: `reports/v2/llm_value/graph_contribution.json`.
- **V2-03 "news→permit-DB" reconstruction** (`ml/forecasting/llm_permitize_value.py`, hypothesis
  REFUTED): tested whether rebuilding news as permit-schema records (precise event_start/end +
  specific borough, `claude_events_permitized_2026h1.jsonl`) recovers value. It **hurt**:
  permitized−A1 = **`MEANINGFUL_NEGATIVE` −6.31%** (CI [−25.2,−5.5]), worse than raw news too
  (WAPE 0.0940 vs 0.0883). **Structure is not the missing ingredient** — the permit feed works
  because of event DENSITY (63,070 events → learnable coefficient); news gives ~19, and making those
  sparse events sharp/confident injects confident noise (a strike may raise or lower bike demand;
  unlearnable from so few). 4 events leakage-dropped (retrospective reviews post-date their event).
  Honest negative, not faked. 8 pure-builder tests. Artifact: `permitize_contribution.json`.
- **V2-03 (a) news-as-importance-weight** (`ml/forecasting/llm_importance_weight_value.py`): keep the
  dense permit feed, let news only modulate it — `ev_active×(1+news_salience)`, unchanged where no
  news. **Also negative: `MEANINGFUL_NEGATIVE` −7.82%** (CI [−25.6,−5.9], WAPE 0.0883→0.0925). Example
  row shows why: Winter Storm Fern amplifies permit 63→119.7, but a blizzard *suppresses* bike demand
  → wrong-signed. Artifact: `importance_weight_contribution.json`.
- **V2-03 (b) H3-grain graph test = `blocked_data`**: fine H3 graph needs geocoded events; real
  permit/news events are borough-tagged only (no coordinates). Not fabricated; borough-grain graph
  null stands as the finest fair test.
- **V2-03 (signed LLM demand signal)** (`ml/forecasting/llm_signed_value.py`): LLM emits signed
  `demand_effect∈[−1,+1]` (blizzard −0.9, festival +0.5, LIRR shutdown +0.6 via substitution) →
  `news_demand_signal = demand_effect×severity×decay`. **LLM sign-correctness 0.77** (direction is
  right), harm removed (−7.82%→−2.04%), but still **`NO_MEANINGFUL_EFFECT`** (CI [−7.26,+1.44], WAPE
  0.0883→0.0906). Reason: autoregressive lags (dep_lag_1/24/168, roll_mean_24) already encode an
  ongoing event's demand → the news signal is **redundant**. 3 more unit tests.
- **V2-03 overall (negative result, fully understood):** five attempts — improve extraction / graph /
  permit-schema reconstruction / importance-weight / signed direction — all neutral-to-negative.
  Three-level why: (a) **sparsity** (~19 events can't teach magnitude), (b) **sign heterogeneity**
  (fixed by a signed LLM effect, 77% correct), (c) **redundancy** (demand-history lags already capture
  ongoing-event shocks). News would only help at the sudden onset of an unanticipated shock before the
  lags react — rare + limited by coarse timing/availability gate. Not just observed — explained.
- **Honesty:** every V2 result cell is `pending`; no v1 number is copied into a V2 claim. v1
  results below remain the current measured record until a V2 phase re-measures them.

## Measured results — event-aware forecasting lift (real data)

The central product claim was tested end-to-end on real data (see `docs/EVENT_LIFT_FINDINGS.md`):
train on Jan–May 2026, hold out June, compare a demand+calendar baseline against the same model given
event-derived features.

- **NYC permitted events → measured improvement.** 20.3M real Citi Bike trips streamed to
  borough×hour, joined with 63,070 real NYC permitted events (leakage-safe, public permit schedule).
  June-holdout WAPE fell **0.1013 → 0.0996 (−1.65% relative)**; paired day-block bootstrap verdict
  **`measured_improvement`**, 95% CI **[0.36, 5.11]** (above zero). Reproduce:
  `python -m ml.forecasting.borough_event_lift`. Model-attributed, not causal; borough grain is a
  documented approximation of the H3 product grain.
- **June weather → honest negative.** Same design with NOAA Central Park weather: WAPE **0.4868 →
  0.4893**, verdict **`negative_lift`** (CI below zero). Mild June has little weather variance; the
  result is reported as-is, not hidden. Reproduce: `python -m ml.forecasting.weather_lift`.

## LLM extraction providers (opt-in)

The event extractor selects a provider by `LLM_PROVIDER` (`config/settings.py`). Demo Mode and all
tests use the deterministic offline `mock`. Two real, opt-in providers now exist behind the same
`LlmProvider.extract(article) -> list[dict]` interface, each lazily imported so the mock path needs
no SDK/key:

- **`anthropic`** (Claude) — `ANTHROPIC_API_KEY` / `LLM_MODEL`.
- **`openai`** (GPT-4o) — `OPENAI_API_KEY` / `OPENAI_MODEL` (default `gpt-4o`); `pip install -e ".[llm]"`.

Both enforce the §8/§22 guardrails identically: forced structured output, verbatim evidence
grounding, deterministic gazetteer geocoding (never model coordinates), bounded severity/confidence,
provenance on every extraction, and honest degrade (raises if the SDK/key is absent — never a
fabricated event). Covered by `tests/unit/test_openai_provider.py` and `test_anthropic_provider.py`.

## GraphRAG operator copilot (V2-08)

The operator "운영 도우미" (`POST /v2/operator/ask`, shown on `/statistics`) now upgrades automatically
when an LLM key is configured. With `LLM_PROVIDER=openai`/`anthropic` + a key it answers via
**GraphRAG**: `services/api/graphrag.py` retrieves the as-of event graph (events + grounded evidence +
affected zones + model-attributed forecast delta — the same ReplayEngine artifacts the dashboards
use) and asks the model to answer *using only that context and citing event ids*. Cited ids are
validated against the context, so the copilot can never surface an event the graph did not contain
(§22). With the default `mock` provider — or a missing SDK/key, or any provider error — it degrades
to the deterministic rule-based `ops_ask`. The response gains `answer_mode`
(`graphrag_llm`/`rule_based`) + validated `citations`; the UI shows a badge and the cited events.
`services/api/llm_chat.py` is the degrading chat helper (test-injectable, offline). Covered by
`tests/integration/test_graphrag_copilot.py`. See `docs/LOCAL_GPT.md` for the local key setup.

## Event graph built from real repo data

`make seed-graph` (`scripts/build_graph.py`) populates the §9 event graph directly from data already
in the repo, so it is no longer a 2-event demo. It combines **news** (`data/fixtures/news_live/*.jsonl`
→ mock extraction, provenance-rich) with **NYC permitted events**
(`nyc_permitted_events_filtered.jsonl.gz`, 63k rows → borough-centroid grounded, spatially rich).
Measured build (`--permitted-limit 2000`): **2,090 events / 5,770 nodes / 11,850 edges / 6 zones**,
replay-idempotent, audit clean; a portable node-link JSON snapshot is written under
`data/processed/graph/` (git-ignored). `--backend neo4j` writes to a live server. The graph remains
an audit/provenance surface (§9); forecasting features stay pure functions off this critical path.

## Current status — V2 usability update (UI, search, operator analytics)

A backward-compatible, usability-focused increment on top of V1. Scope: a redesigned rider home in
the style of consumer bike-share apps, station **search**, and a stronger **operator statistics /
analytics** screen. No forecasting/pricing/experiment claims change — everything stays offline and
honestly labelled as the `demo-heuristic-v1` demo heuristic (not a measured Phase 06 model).

- **Rider home redesign** (`apps/web/app/page.tsx`) — prominent search bar, availability summary +
  filter chips (전체 / 빌리기 좋아요 / 곧 부족), a clean station list, and a tap-to-open station
  detail sheet with the event-aware demand shift and a "why busy" trace link.
- **Station search** — new offline endpoint `GET /v2/rider/stations/search` (Korean / English /
  alias / typo-tolerant substring match over `data/fixtures/station_gazetteer.json`), which
  hydrates each hit with as-of live inventory from the operational fixture (never inferred from the
  query text). Empty query returns all stations ranked by availability.
- **Operator statistics** — new endpoint `GET /v2/operator/statistics` (real aggregations: system
  utilization, availability distribution, shortage load, event mix by type/effect, demand-delta
  spread, per-zone breakdown) rendered on a new `/statistics` screen with a stacked availability
  bar, event-type / top-surge bar lists, and a per-zone table. All values reconcile with the v1
  endpoints and respect the as-of leakage boundary.
- **Event-window timeline** — new endpoint `GET /v2/operator/timeline` recomputes the as-of
  aggregates (shortage, Δ, event count) at each hour across the replay window (12:00→18:00) with
  event-onset markers, rendered as two inline-SVG area+line charts on `/statistics`. Shows the
  leakage boundary visually (flat until onset) and `event_count` is monotonic non-decreasing.
- **Optimal extra-bike allocation** — new endpoint `POST /v2/operator/rebalancing/allocate` and
  `optimization/classical/allocation.py`: the operator inputs **M** extra bikes and the allocator
  distributes them to maximise benefit under the asymmetric objective (shortage 3 : overflow 1),
  respecting dock capacity and `Σ added ≤ M`. Objective is separable/convex so greedy is globally
  optimal (validated against brute-force enumeration). Surplus bikes with no beneficial placement
  are honestly held back, not force-placed. Rendered as a "추가 자전거 최적 분배" planner on
  `/rebalancing` with an M input.
- New code: `services/api/v2.py`, `data/fixtures/station_gazetteer.json`,
  `apps/web/app/statistics/page.tsx`; endpoints wired in `services/api/app.py`; typed client in
  `apps/web/lib/api.ts`.
- Tests: **18 new** integration tests in `tests/integration/test_api_v2.py` + **7** unit tests in
  `tests/unit/test_allocation.py` (search matching, live hydration, as-of boundary, statistics
  consistency, timeline onset/monotonicity, allocation optimality vs. brute force, honest hold-back)
  — all pass. Full non-torch suite: **204 passed, 1 skipped**; web `tsc` clean, `next build` green
  (12 routes), ruff + mypy clean on the new modules. The 9 `torch`-dependent recsys/model tests
  can't run here (the PyTorch wheel index is blocked by the container proxy) — they are unrelated
  to this change.
- **Rider / operator experience split** — a top-level role switch (🚲 라이더 / 🛠 운영자, persisted).
  Rider mode is a clean consumer view (operator tools hidden, read-only replay clock); operator mode
  shows the full tool tab bar + replay control. Deep-links to operator routes auto-select operator
  mode. Plus a **Noto Sans KR** gothic font (self-hosted via `next/font`) for Korean readability.
- **Rider map view** — a ☰ 목록 / 🗺 지도 toggle on the rider home; the map is a self-contained SVG
  that projects stations by real lat/lng (offline, no tile provider / API key), colours markers by
  availability with 🔥 surge rings, and opens the station detail sheet on click.
- **Rider copilot** — a no-LLM natural-language ask on the rider home (`POST /v2/rider/ask`).
  A deterministic parser (`services/api/rider_copilot.py`) classifies a Korean/English query into an
  allowlisted intent and answers **only from live tool results** (numbers copied verbatim, nothing
  fabricated); unsupported queries return a clarification, not a made-up answer.
- **Dynamic fare simulator** (V2-05) — a bounded scarcity surcharge (1.00/1.10/1.25/1.50) +
  balancing credit, as a **SIMULATED SHADOW** quote (never applied to a rider). Pure kernel
  (`ml/pricing/dynamic.py`) with guardrails enforced in-kernel: safety/emergency event → base,
  stale data → base, hard 1.50 cap, `base + surcharge == final` (auditable), and **no rider
  identity / reduced-fare / protected attribute** ever used. Operator `/pricing` screen with what-if
  scenario toggles. `POST /v2/pricing/quote`.
- **Dynamic-fare revenue comparison** (V2-05) — `make v2-evaluate-revenue`
  (`ml/pricing/revenue_eval.py`) prices flat vs event-aware dynamic over the **real shipped
  `/v2/pricing/quote` path** (replay engine as-of a post-event cutoff) and adds a revenue layer with
  an **explicit demand-elasticity** model. Measured (SIMULATED SHADOW): at elasticity 0.5, event-aware
  dynamic yields **+0.4% network revenue with zero lost rentals** (the surcharge fires only at
  supply-constrained event zones, capturing value on bikes that sell out anyway). An **elasticity
  sweep** (0→1.5) shows the uplift is robust, and an **event-severity what-if** (×1/×2/×3) shows
  revenue rising with event intensity (uplift +0.4%→+1.0%→+1.5%, surcharge tier 1.10×→1.25×) while
  flat pricing leaves that value on the table. Report: `reports/v2/pricing/revenue_sim.json` (+`.md`).
- **Ops copilot** (V2-07) — an operator NL assistant (`POST /v2/operator/ask`). A deterministic
  parser maps a query to an allowlisted intent and answers **only from the dashboard artifacts**
  (`operator_statistics` / `pricing_quotes`) — no arbitrary SQL, no fabricated numbers; facts are
  asserted to match the statistics endpoint. Answers can return a **deep-link** to the matching
  screen. Rendered as a card on `/statistics`.
- **Hybrid geo-semantic search** (V2-03) — provider-based (`GET /v2/rider/search/hybrid`): BM25 +
  char-n-gram vector + geo, fused with RRF; hits re-hydrated from the operational store. Offline
  `LocalHybridProvider` is the tested path; optional `ElasticsearchProvider` degrades to local when
  unavailable. `make v2-evaluate-search` reports Recall@10 / MRR / NDCG@5 / geo-valid (all 1.0 on the
  gold set).
- **Predictive lift protocol** (V2-02) — pure, tested machinery (chronological split + purge/embargo,
  event-block bootstrap CI, honest verdict rule). The demo run (`GET /v2/model/predictive-lift`,
  `make v2-evaluate-predictive-lift`) measures real coverage and honestly reports **`blocked_data`**
  (demo fixture far below the gate); a measured claim needs a real news backfill + training. Surfaced
  in the Model Lift Lab.
- **Real Citi Bike network (45 stations)** — the operational fixtures now carry **40 real Citi Bike
  stations** imported from GBFS `station_information`/`station_status` plus the **5 Jersey City /
  Hoboken event-zone stations** (also real) kept so the golden-path event demo still drives a
  shock. Everything (search, map, stats, pricing, allocation, copilots) runs on this network; the
  labelled pricing/switchback *simulation* is decoupled to the 5 event-zone stations so it stays
  deterministic regardless of the imported live network.
- **Real station import (GBFS)** — `make v2-import-stations` / `POST /v2/operator/stations/import`
  pulls the **real Citi Bike network** from GBFS `station_information` (free, no key) into the
  fixtures. `--from-file` / `--status-file` import a locally-downloaded feed when the host has no
  egress; degrades gracefully. Preview button on the operator statistics screen.
- **On-demand live news sync** — a "뉴스 동기화" button (`POST /v2/news/sync`) pulls real news from
  **GDELT DOC 2.0** (free, no key) and accumulates it into the vector store. Labelled `live` only
  when it truly fetched; a network failure returns `degraded` with the reason and **no fabricated
  articles** (offline sandbox → degraded; deploys with egress → live).
- See `docs/V2_UX_UPDATE.md` for the full spec and reproduction steps.

---

## Previous status — V1 complete (with honest data blocks)

**v0 (Phases 00–09) complete**, and **V1 (V1-00 … V1-09) implemented** on top as backward-compatible
increments. See `docs/V1_EXECUTION_LOG.md` for per-phase detail and `reports/v1/V1_FINAL_AUDIT.md`
for the final audit.

- Done: V1-00 contracts · V1-01 news backfill (+ **real GDELT** opt-in) · V1-02 incremental features
  (== full rebuild) · V1-03 model registry (measured B0-B4) · V1-04 event-lift gate · V1-05
  live-shadow (pending labels) · V1-06 anomaly detection · V1-07A–D recommendation + pricing
  (measured retriever / simulated policy) · V1-08 clustered-switchback experiments (simulated) ·
  V1-09 UI (8 screens) + offline golden-path E2E + audit + packaging. Plus a **FAISS news vector
  store** (accumulating news, semantic search, same-event clustering).
- Honest blocks: **event lift** = `insufficient_event_overlap` (claim disabled); **real-news
  coverage** = `BLOCKED_DATA` until a real backfill passes the gate; **recommendation / pricing /
  experiments** = `simulated`; **live-shadow** predictions = `pending`.
- Tests: **199 passed, 1 skipped** (`make test`); web `tsc` clean; ruff clean; offline E2E green.
- Commands verified: see the `make` targets below (each runs a real, tested workflow).

---

## v0 milestone detail (Phases 00–09)

**Phase 08 — Rebalancing & Quantum Research Mode: complete.** (Phases 00–07 also complete.)

### Phase 08 — Rebalancing & Quantum Research Mode (complete)

Implemented `optimization/classical/` and `optimization/quantum/` (§14) plus the API/UI wiring:

- **Classical** (`problem.py`, `objective.py`, `feasibility.py`, `greedy.py`, `enumeration.py`,
  `milp.py`, `config/rebalancing.py`) — asymmetric operational objective (shortage > overflow,
  3:1) over post-plan inventory; explicit feasibility checks (outflow ≤ bikes, final ≤ capacity,
  non-negative integer moves, vehicle-capacity limit) that report infeasibility in plain text;
  greedy baseline (always feasible), exact **MILP** via `scipy.optimize.milp`, and an enumeration
  oracle. Verified: **MILP cost == enumeration cost** (optimal) and ≤ greedy; binding vehicle
  capacity respected.
- **Quantum Research Mode** (`qubo.py`, `qaoa.py`) — small instance → QUBO with a documented
  bounded-binary variable mapping and a quadratic imbalance surrogate energy. **QUBO brute-force
  optimum == exact enumeration optimum** (required, §14.2), encoding matches the surrogate for
  every bit vector, and on a crafted instance the QUBO plan coincides with the MILP plan. QAOA is
  optional (lazy `qiskit`); qiskit is absent here, so its test skips with a documented reason.
  Research only; simulator ≠ hardware; no advantage claim.
- **API/UI** — `POST /v1/rebalancing/solve` now returns a typed, feasibility-checked plan
  (`services/api/rebalancing.py`, `schemas.py`, `app.py`); the 501 is gone. Targets are raised in
  event-exposed zones by the `demo-heuristic-v1` forecast delta as-of the cutoff (labelled demo
  heuristic, not the measured model). `apps/web/app/rebalancing/page.tsx` renders the plan.
  `make rebalance-demo` runs the whole thing offline.

### Phase 07 — FastAPI & Next.js UI (complete)

- **API** (`services/api/`) — offline FastAPI replay service: `/v1/health`, `/v1/replay/state`,
  `/v1/replay/set-cutoff`, `/v1/events`, `/v1/forecasts`, `/v1/zones/{id}/explanation`,
  `/v1/scenarios`, `/v1/rebalancing/solve`. Every response carries mode/cutoff and model/feature
  versions; explanations are evidence-backed; the demo forecaster is the labelled
  `demo-heuristic-v1` (Historical Replay), kept distinct from the measured Phase 06 model.
- **UI** (`apps/web/`) — Next.js App Router, TS strict: Control Tower, Why Changed, Scenario Lab,
  Rebalancing Planner. Consumes the API; Historical Replay vs Live visually distinct.

### Phase 06 — Forecasting, Tuning & Evaluation (complete)

Implemented `ml/forecasting/` (§11): a seasonal-naive baseline, a six-algorithm model zoo,
rolling-origin temporal CV, GridSearch tuning, permutation-importance feature selection, the
B0–B4 ablation, and the §11.4 metrics — run on the real June-2026 data.

- **No leakage in evaluation** (`splits.py`) — the latest 72h are an untouched out-of-sample
  test; GridSearch cross-validates on the earlier span with 3 expanding-window folds; imputation
  and scaling are fit per fold. Random K-fold is never used (§11.3).
- **Model zoo + GridSearch** (`models.py`, `config/forecasting.py`) — ridge, knn, random_forest,
  extra_trees, gradient_boosting, hist_gradient_boosting, each with a tuned grid; seed 42.
- **Metrics** (`metrics.py`) — WAPE (defined zero-denominator), MAE, MASE (explicit seasonal
  scale), event-window WAPE, peak-direction accuracy, forecast-delta stability.
- **Feature selection** (`feature_selection.py`) — permutation importance on the test holdout;
  the top-12 reduced model matches the full 32-feature model.
- **Honest event ablation** — the runner verifies (not assumes) that as-of event/graph features
  are zero on the June window (curated events postdate the data, §5.2), so B2–B4 reproduce B1.
  Reported plainly (§11.4, §22); interpretation and figures in `README.md` / `docs/`.

### Phase 05 — As-of Graph Feature Builder (complete)

Implemented `pipelines/features/graph_features.py` + `kernels.py` (§10, §5.2):

- **Pure kernels** (`kernels.py`) — `haversine_km`, `exp_distance_decay`, `half_life_weight`;
  side-effect free and unit-tested (§10 "mathematical kernel as pure functions").
- **Builder** (`build_graph_features`) — for a `forecast_cutoff`, emits per-zone
  `FeatureSnapshot`s using ONLY events with `available_at <= cutoff` (§5.2). Produces the §10
  feature set: `event_count_{6,24}h_by_type`, `source_weighted_severity`, `unique_source_count`,
  `duplicate_article_ratio`, `confidence_mean/max`, `distance_decayed_impact`,
  `time_to/since_event_start`, `event_remaining_duration`, `neighbor_zone_impact`,
  `capacity_shock_exposure`, `transit_disruption_exposure`. Preserves `source_event_ids`.
- **Config-reproducible** (`config/graph_features.py`, `GraphFeatureConfig`) — half-life,
  radius, decay scale, hops, source weights, confidence floor, feature version. Same events +
  same cutoff + same config → identical output.

### Phase 04 — Neo4j Graph Upsert (complete)

Implemented `pipelines/graph/` — a backend-neutral event graph (§9):

- **Model** (`model.py`) — `build_graph_ops` turns events + their source articles into the §9
  node/relationship set: Article, Event, EventType, Place, H3Zone, Source (Station reserved),
  wiring `Event -[:AFFECTS]-> H3Zone` via `Event -> Place -> H3Zone` so the graph feeds numeric
  features (a graph that couldn't is forbidden decoration, §9). A small place gazetteer
  (`config/places.py`) lets the mock extractor attach grounded locations to events.
- **Stores** (`store.py`, `neo4j_store.py`) — a `GraphStore` interface with an **offline
  in-memory** backend (idempotent MERGE semantics; Demo/tests need no DB) and an optional
  **Neo4j** backend using parameterized, idempotent Cypher (lazy driver import, `.[graph]` extra).
- **Cypher** (`cypher.py`) — pure, unit-tested builders: one uniqueness constraint per label
  (`IF NOT EXISTS`), MERGE-on-key node upserts, MERGE relationship upserts. Labels/rel-types
  come from a fixed allowlist; no value interpolation.
- **Audit** — flags orphan nodes and events lacking provenance (both zero on the demo graph).

### Phase 03 — LLM Event Extraction (complete)

Implemented `pipelines/events/` with a provider interface and a deterministic mock (§8):

- **Provider** (`provider.py`) — `LlmProvider` ABC + `MockLlmProvider`: keyword-ontology
  extractor, no network/key. Same fixture + prompt version → identical output; stable event ids.
  Evidence spans are exact substrings of the article (grounded); per-type demand/capacity effect
  is directional only (e.g. transit disruption → bike demand *increase*), severity is a bounded prior.
- **Extractor** (`extractor.py`) — validates candidates with Pydantic under **bounded retries**,
  verifies evidence grounding, sets accept/quarantine/reject from a configurable confidence
  threshold, and **deduplicates** near-identical events (token-Jaccard, merging provenance).
  Rejected/quarantined events are kept (auditable); the final validation error is recorded on failure.
- Config (`config/events.py`): keyword ontology, effect priors, thresholds, dedup — all tunable.

### Phase 02 — Demand Aggregation & Feature Store (complete)

Implemented the demand feature pipeline in `pipelines/features/`:

- **Temporal kernels** (`temporal.py`) — pure functions localizing naive wall-clock times to
  `America/New_York` with **explicit DST handling**: spring-forward (nonexistent) times are
  shifted across the gap, fall-back (ambiguous) times resolve to the earlier occurrence — never
  silently dropped (§5.3). Plus local-hour flooring and a gap-free hourly index that yields the
  correct 23/25-hour DST days. The Citi Bike collector now uses this localization too.
- **Zone assignment** (`zones.py`) — H3 res-9 cell per coordinate (§4), thin wrapper over `h3`.
- **Aggregation** (`aggregate.py`) — trips → `DemandCell` at the primary grain (H3 zone × local
  hour): departures at start, arrivals at end, `net_flow = arrivals - departures`. New contract
  `DemandCell` (§4, §6).
- **Leakage-safe features** (`lags.py`) — per-zone dense hourly reindex (missing hours = 0),
  lag features (1h/24h/168h) and shifted rolling means (3h/24h). Every feature at hour t uses
  strictly hours < t; the current target never enters its own feature; no wrap across zones (§5.4).
- **Calendar features** (`calendar.py`) — completes ablation B1's "calendar" layer (§11.2):
  hour-of-day, day-of-week, weekend, morning/evening rush, US federal holiday, and cyclical
  (sin/cos) encodings for hour and weekday. These describe the target hour and are leakage-free.
  Total feature width is now 25 (15 lag/rolling + 10 calendar) plus 3 labels.

## Commands verified

Run on this machine (Python 3.12.10 local; also verified on Python 3.11.15 + Node 22 in the
web/CI sandbox), `.venv`:

- `ruff check .` — passed
- `ruff format --check .` — passed (95 files)
- `mypy .` — passed (no issues, 95 source files)
- `pytest` — **114 passed, 1 skipped** (the skip is the optional QAOA test; qiskit absent).
- `make rebalance-demo` (`python -m optimization.demo`) — offline; at cutoff 15:30 greedy and
  MILP both move 8 bikes (cost 42.0 → 17.70, shortage 8 → 0, feasible); enumeration optimum
  matches the MILP; the single-edge QUBO brute-force energy equals exact enumeration (match=True).
- `apps/web`: `npm run typecheck` and `npm run build` — passed under TS strict (Next.js 15, Node 22).
- `make evaluate` (`python -m ml.forecasting.run <June zip>`) — offline; rolling-origin over
  30,947 usable rows / 139 zones. Best by CV WAPE: **knn** (`n_neighbors=30`, `weights=distance`),
  test WAPE 0.516, MASE 0.794 (beats B0 seasonal naive WAPE 0.658 / MASE 1.013). All 6 algorithms
  beat B0; top-12 reduced model matches the full 32-feature model. The domain-customised OCS
  (shortage-weighted) reorders the board (extra_trees best, knn worst learned model). Ablation
  B1=B2=B3=B4 (event features verified zero on the June window). See `README.md` and `reports/phase06_*`.
- `make graph-upsert-demo` — offline; 2 events → 15 nodes / 17 edges; idempotent replay; audit
  clean; events link to 3 H3 zones.
- `make graph-features-demo` — offline; shows the as-of boundary: cutoff 13:59 → 0 snapshots
  (transit event not yet available); 14:30 → 2 zones (transit_disruption_exposure ≈ 0.63);
  15:30 → 3 zones as the concert becomes available and the transit event decays.
- EDA on the real June-2026 data (`docs/EDA.md`, `docs/STATISTICAL_TESTS.md`): derived 7
  leakage-safe features (surge momentum, zone expanding mean, same-day net-flow pressure, and
  two member-share composition lags); feature width now **32**.
- Statistical verification (scipy): weekday vs weekend is driven by **timing** (evening rush
  Cohen's d = 2.20) and **rider composition** (member share d = 2.72, p = 1.4e-4), not by daily
  totals (Welch p = 0.15). Day-of-week significant (Kruskal p = 0.017); rideable_type not
  significant for rush (chi-square p = 0.50) → deliberately not added as a feature.
- Visual EDA report published as an Artifact (offline, self-contained; charts + tests).
- `make collect-demo` — runs fully offline (see prior phase output).
- `make build-features` (`python -m pipelines.features.demo`) — offline on the sample fixture:
  trips=4, demand_cells=7, feature_rows=7, zones=4.
- `make extract-events-demo` (`python -m pipelines.events.demo`) — offline; from 3 fixture
  articles: 2 accepted events (TRANSIT_DISRUPTION → demand increase; LARGE_VENUE_EVENT), 0
  errors, evidence grounded; the neutral article yields no event.
- `make v2-evaluate-revenue` (`python -m ml.pricing.revenue_eval`) — offline; flat vs event-aware
  dynamic revenue on the real quote path (SIMULATED SHADOW). Headline (elasticity 0.5): flat 362.00
  vs dynamic 363.40 → **+0.4% revenue, 0 lost rentals, 7 surcharged**; elasticity sweep flat
  (supply-constrained); event-severity what-if ×1/×2/×3 → uplift +0.4%/+1.0%/+1.5%, tier
  1.10×/1.25×/1.25×. Report `reports/v2/pricing/revenue_sim.json`.
- `python -m ml.forecasting.run` (no zip) — offline; writes an honest **`blocked_data`**
  `reports/phase06_results.json` (0 usable rows after the 7-day warm-up on the sample) instead of
  crashing, and prints the real-run command.

## Tests passing / failing

- Unit: `test_contracts.py` (19), `test_settings.py` (3), `test_temporal.py` (6),
  `test_demand_features.py` (12), `test_calendar.py` (5), `test_event_extraction.py` (9),
  `test_graph_features.py` (10, incl. the **14:01→14:00 leakage regression**) — passing.
- Integration: `test_collectors.py` (8), `test_graph.py` (9), `test_api.py` (10 — as-of boundary
  through HTTP, evidence-backed explanations, scenario toggle, **feasible rebalancing plan**) —
  passing.
- Rebalancing/optimization: `test_rebalancing.py` (6 — pure objective, feasibility rejection,
  greedy feasibility, MILP == enumeration and ≤ greedy, binding vehicle capacity), `test_qubo.py`
  (6 + 1 skipped — bounded encoding coverage, QUBO == surrogate energy, **QUBO == enumeration
  optimum**, QUBO == MILP plan on crafted instance, QAOA degrades without qiskit).
- Forecasting: `test_forecasting.py` (10) — WAPE/MASE zero-denominator behaviour, seasonal-naive
  fallback, and the rolling-origin guarantee that every training fold precedes its validation
  window (no temporal leakage, §11.3).
- Temporal coverage includes **DST spring-forward and fall-back** cases (§5.3) and the
  **lag/rolling leakage** guarantees (§5.4), including "changing the current value does not
  change any past feature".

## Measured results available

- **Real-data run** on `JC-202606-citibike-tripdata.csv.zip` (June 2026, git-ignored per §7.1),
  full pipeline in ~4.7s:
  - collection: total=109,897, accepted=109,510, excluded=387 (all `missing_coordinate`, verified).
  - aggregation: **40,479 demand cells across 208 H3 zones**.
  - features: 40,479 rows; 30,947 have a 1-week (168h) lag available.
  - busiest cell: 2026-06-09 17:00 (evening rush) — departures=87, arrivals=13, net=-74.
- **Forecasting (Phase 06)** on the same data (rolling-origin, seed 42; `make evaluate`):
  - dev 26,918 / out-of-sample test 4,029 rows (last 72h), 3 expanding CV folds, 32 B1 features.
  - leaderboard (test WAPE): extra_trees 0.492, gradient_boosting 0.497, hist_gb 0.497,
    random_forest 0.505, knn 0.516, ridge 0.527; B0 seasonal naive 0.658. CV-selected model: knn.
  - top features by permutation importance: `dep_lag_1`, `dep_lag_168`, `arr_lag_1`, `dep_lag_24`,
    `cal_hour_cos`, `cal_is_evening_rush` — short-term persistence + weekly seasonality + rush timing.
  - **OCS (domain-customised, shortage-weighted 2:1) reorders the board**: the CV-WAPE pick knn is
    the *worst* learned model on OCS (0.857) because it under-forecasts most; extra_trees is best
    on OCS (0.781). All models under-forecast (negative bias) → structural stockout risk.
  - event ablation collapses to B1: 0 graph snapshots at the last June cutoff (verified, §5.2).

## Known blockers / notes

- Local `.venv` uses Python 3.12.10 (repo pins `>=3.11`; machine lacks 3.11).
- News and GBFS are still fixtures/samples (real news feed deferred by user; GBFS live is opt-in).
- Console output is ASCII-only for Windows cp949 compatibility.
- **Event lift not demonstrable on the June window**: curated events postdate the trip data, so
  the as-of event/graph features are zero and B2–B4 = B1 (verified, not assumed). See
  `docs/KNOWN_LIMITATIONS.md`. `make evaluate CITIBIKE_ZIP=…` runs the full B0–B4 ablation on a real
  trip backfill deep enough to survive the 7-day-lag warm-up and leave the rolling-origin holdout;
  the tiny sample fixture lacks that history, so `ml/forecasting/run.py` now writes an honest
  **`blocked_data`** marker (no fabricated metrics, exact real-run command printed) to a separate
  file instead of crashing or clobbering a measured `reports/phase06_results.json`.
- **Relational store (opt-in `[rdb]`)** — `services/db/` (SQLAlchemy Core) persists the station
  network + inventory snapshots + a load-audit trail into **SQLite by default** (`make db-load`,
  zero-config, offline) or **Postgres** via `DATABASE_URL` — same code, parameterized statements,
  idempotent upsert, non-destructive `init`. Verified end-to-end: 45 stations loaded from the JSON
  fixtures with resolved H3 zones, idempotent re-load. `tests/integration/test_db.py` (in-memory
  SQLite, skips without the extra).
- **Live Neo4j graph (opt-in `[graph]`)** — a `build_graph_store()` factory selects the backend:
  offline `InMemoryGraphStore` by default, live `Neo4jGraphStore` when `NEO4J_PASSWORD` is set
  (`make graph-upsert-neo4j`, `--backend neo4j`). `docker-compose.yml` provisions Neo4j (and
  Postgres) for local dev. The forecasting graph features are pure functions and never depend on the
  graph DB — Neo4j is the §9 upsert/audit surface only. Factory selection is unit-tested
  (`tests/unit/test_graph_factory.py`); the live-server path needs Docker (not exercised in-sandbox).
- **Real LLM event extraction (opt-in)** — a Claude-backed `AnthropicLlmProvider`
  (`pipelines/events/anthropic_provider.py`, `LLM_PROVIDER=anthropic`, `make evaluate … --provider
  anthropic`) alongside the deterministic mock. Structured output via strict tool use; **evidence
  kept only when it is an exact substring of the article** (ungrounded events dropped); geocoding
  stays deterministic via the gazetteer (never model coordinates); severity/confidence clamped;
  model id + prompt version on every extraction. Demo Mode and all tests keep the mock default; the
  real provider is lazy and **degrades to a per-article error (never a fabricated event)** without
  the SDK/key. Needs `pip install anthropic` + `ANTHROPIC_API_KEY` (or `ant auth login`).
- **Real event-lift path is now fully wired** (previously the B2–B4 columns were hard-coded to 0):
  `load_real_panel(source, news_source=…)` / `python -m ml.forecasting.run <trip> --news <news.jsonl>`
  joins the real as-of graph features into the ablation columns, leakage-safe (an event first
  available at H contributes 0 to every row before H — pinned in `tests/unit/test_dataset_event_join.py`).
  With no `--news` the columns stay identically 0 (the honest zero-overlap baseline). To *measure* a
  positive LLM-feature lift you still need a news backfill whose availability overlaps the trip
  window and passes the V2-01 coverage gate; that data isn't in this offline sandbox, but the code
  path now produces real B2–B4 features the moment it is supplied.

## Known blockers / notes (Phase 08)

- `qiskit` is not installed in this environment; the QAOA path is exercised only as its
  "unavailable" branch and its test is skipped with a documented reason (§14.2). Everything else
  in Quantum Research Mode (QUBO build + brute-force + enumeration validation) runs without it.
- The rebalancing station inventory is a curated fixture (`data/fixtures/rebalancing_demo.json`);
  targets use the labelled demo heuristic, not the measured Phase 06 model. See
  `docs/KNOWN_LIMITATIONS.md`.

## Next phase input contract

**Phase 09 — Final Audit & Portfolio Packaging** consumes the completed Phases 00–08 and:
- Syncs documentation to the implementation (`docs/PRD.md`, `ARCHITECTURE.md`, `DATA_CONTRACTS.md`,
  `GRAPH_SCHEMA.md`, `OPTIMIZATION.md`, `DEMO_SCRIPT.md`, `EVALUATION_PROTOCOL.md`,
  `KNOWN_LIMITATIONS.md`, `STATUS.md`, `README.md`).
- Runs the final honesty audit (no fabricated metrics, no causal claims from feature attribution,
  no quantum-advantage claims, fixture vs live vs measured clearly separated) with the full gate
  green, per §18 and §23.
