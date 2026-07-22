# V2 Execution Plan — Phases V2-00 … V2-09

Each phase below lists **goal · acceptance criteria · completion artifact · reproduction command**.
Phase gates are honored: do not advance until acceptance criteria are met, relevant tests pass,
docs reflect actual behavior, and outputs are real. `Status` starts at `PLANNED` for every phase;
update it only from an executed command or a committed artifact.

Legend for `Status`: `PLANNED` → `IN_PROGRESS` → `PASSED` / `PASSED_BLOCKED_*` / `BLOCKED`.

---

## V2-00 — Audit & Domain Correction
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** Reconcile repo against V2 addendum; confirm domain is Citi Bike / NYC everywhere;
  inventory which v1 artifacts are re-usable vs must be re-measured; define the result envelope.
- **Acceptance:** No Seoul/ParcelFlow/parcel references in active code/docs; `claim_status`
  envelope defined in `contracts/v2/`; stale-number audit lists every doc figure and its source.
- **Artifact:** `reports/v2/final/v2_audit.md` (audit table) + envelope contract committed.
- **Command:** `make v2-audit` → exit 0 (2 gates PASS). Envelope tests: `pytest tests/unit/test_v2_envelope.py` → 22 passed.
- **Delivered:** `contracts/v2/{enums,envelope}.py` (`ClaimStatus` 9-value + `ResultEnvelope`);
  `scripts/v2_audit.py`; `reports/v2/final/v2_audit.md`. Findings: domain clean (0 drift);
  recorded JC-vs-NYC nuance; flagged test-count inconsistency (114/199/200/204 across docs) and
  legacy `v2-*` phase-number collision.

## V2-01 — Measured Model Productization & H3 Multi-Holdout
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** Promote a measured forecasting model artifact and serve it in non-demo modes;
  evaluate it across multiple rolling H3 holdout windows (not a single split).
- **Acceptance:** Promoted model manifest referenced by the API; ≥3 rolling-origin holdout
  windows with WAPE/MAE/MASE reported per window and aggregated; no random split; leakage tests pass.
- **Artifact:** `reports/v2/holdout/h3_multiholdout.json` + `promoted_model.json` + `README.md`.
- **Command:** `make v2-holdout`. See `V2_EVALUATION_PROTOCOL.md`.
- **Delivered (measured):** `ml/forecasting/h3_multiholdout.py` (runner) + `promoted.py` (serving
  loader). Real JC Citi Bike Mar–Aug 2024, 210,042 H3 rows / 234 zones, 3 rolling monthly windows.
  Promoted `hist_gradient_boosting`; aggregate **WAPE 0.4828 ± 0.0030, MASE 0.7996** (beats B0
  seasonal-naive ~0.648 every window). Leakage guard + window/aggregate tests:
  `pytest tests/unit/test_v2_multiholdout.py` → 5 passed.
- **Honest scope / carry-forward:** JC slice (not NYC-wide); B1 (demand+calendar) features only
  (events B2–B4 = V2-03); promotion pool bounded to `ridge`+`hist_gradient_boosting`
  (`--algos all` = full zoo); API serving wiring lands in **V2-07** (loader contract ready now).

## V2-02 — Profit / Regret Ledger
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** Translate forecast error into money: expected shortage cost, overflow cost,
  relocation cost, and regret vs Oracle upper bound.
- **Acceptance:** Contribution margin and shortage externality kept separate; no double-count of
  lost margin; assumptions loaded from a versioned `config/v2/` assumption set; Oracle labeled as
  offline upper bound.
- **Artifact:** `reports/v2/ledger/profit_regret.json` + `reports/v2/ledger/README.md`.
- **Command:** `make v2-ledger`. See `V2_PROFIT_REGRET_LEDGER.md`.
- **Delivered:** `optimization/ledger.py` (pure accounting) + `ledger_run.py` (runner) +
  `contracts/v2/ledger.py` (typed) + `config/v2/assumptions.yaml` (`v2-assumptions-1`).
  Result: promoted forecast nets **+$103,271** vs seasonal-naive over 114,079 zone-hour decisions
  (sign robust across all 9 cost settings), regret vs Oracle **$218,697**. Units measured, dollars
  `simulated`. Tests: `pytest tests/unit/test_v2_ledger.py` → 8 passed (no-double-count, Oracle
  upper-bound/regret≥0, better-forecast-earns-more).
- **Honest scope / carry-forward:** single-period **stocking** economics only — **relocation = 0**
  (origin→destination moves = V2-04 MPC); dollars stay `simulated` until assumptions are sourced.

## V2-03 — LLM Incremental Value Ablation
- **Status:** ✅ PASSED (2026-07-20) — honest null (`insufficient_event_overlap`)
- **Goal:** Separate **No-Event**, **Rule-Event**, and **LLM-Event** feature sets and measure the
  incremental predictive lift and the incremental profit of each — net of LLM cost.
- **Acceptance:** Three ablation arms share identical cutoffs/splits; lift reported with a CI;
  LLM incremental token/$ cost included; honest reporting if LLM adds no lift over the rule arm.
- **Artifact:** `reports/v2/llm_value/incremental_value.json` + `README.md`.
- **Command:** `make v2-llm-value`. See `V2_LLM_VALUE_ABLATION.md`.
- **Delivered:** `ml/forecasting/llm_value.py` (3-arm A0=B1/A1=B2/A2=B4, shared promoted model +
  splits, block-bootstrap CI, ledger profit, LLM cost model). Real JC 2026 H1 + real GDELT NYC
  2026 news (371 articles). **Result:** all arms identical, ΔWAPE=0 CI[0,0], event coverage 0.3%
  → **`insufficient_event_overlap`** (`blocked_data`); LLM actual $0 (mock), est real $0.0061,
  **net LLM value −$0.01**. Tests: `pytest tests/unit/test_v2_llm_value.py` → 6 passed.
- **Borough re-measurement (NYC), the FAIR test:** `ml/forecasting/llm_value_borough.py`
  (`make v2-llm-value-borough`) streamed **19.9M real NYC trips** to borough×hour with 5-month
  training (Jan–Apr), citywide news attribution (4→35 articles), testing **May** (June's window
  had 0 attributable news; May has 216 news rows). Arms A0 / A1 (+permitted) / A2 (+LLM news):
  **A1−A0 = measured_improvement** (WAPE 0.1069→0.1047, CI [1.87, 5.88], +$33k — structured events
  help, reproduces v1 robustly); **A2−A1 = negative_lift** (WAPE 0.1047→0.1075, CI [−6.02, −3.71],
  **net LLM value −$23,730**). Tests: `tests/unit/test_v2_llm_value_borough.py` → 4 passed.
- **Real-LLM extraction (decisive):** to remove the mock-quality confound, claude-opus-4-8 (this
  session) hand-extracted 23 clean, grounded NYC events from the 371 articles
  (`data/fixtures/news_live/claude_events_2026h1.jsonl`; `--claude-events` path). Re-run (test May,
  336 clean news rows): A1−A0 **measured_improvement** (0.0908→0.0883, CI [1.08,6.71]); A2−A1
  **still negative_lift** (0.0883→0.0905, CI [−5.32,−1.56], net LLM value −$17,789).
- **Honest V2 answer (this data):** the **structured permitted-event feed is worth money**; the
  **LLM-from-news layer is net-negative even with a real high-quality LLM extraction** — news
  events are sparse, temporally coarse, and redundant with the dense official permitted schedule,
  so they add variance not signal. The negative is NOT an extraction-quality artifact. Caveat:
  borough event effect is small (~0.002 WAPE) & sample-sensitive; a finer grain with geo-precise,
  higher-frequency events would be a stronger test (not available in this news corpus).

## V2-04 — Multi-period MPC Decisioning
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** Compare the four mandatory policies over a multi-period horizon on the ledger objective.
- **Acceptance:** `No Action`, `Greedy`, `Single-period MILP`, `MPC` all run on the same
  instances; every plan feasibility-checked; infeasibility reported explicitly; MPC uses the
  forecast horizon, not future truth.
- **Artifact:** `reports/v2/mpc/policy_comparison.json` + `README.md`.
- **Command:** `make v2-mpc`. See `V2_MPC_DECISIONING.md`.
- **Delivered:** `optimization/mpc.py` (receding-horizon simulator reusing greedy/MILP solvers) +
  `mpc_run.py`. Result (8 zones, 72h, seeded scenario, ledger cost — lower better): No Action
  1126.7 / Greedy 1154.7 / MILP 1086.9 / **MPC 740.3** / Oracle 718.7. **MPC best feasible**
  (regret 21.6 vs Oracle, ~3%); halves shortage+overflow vs single-period; Greedy net-harmful
  here. MPC uses forecast only (no leakage); Oracle = offline bound (regret ≥ 0); all feasible.
  Dollars `simulated`. Tests: `pytest tests/unit/test_v2_mpc.py` → 7 passed.

## V2-05 — Dynamic Pricing & Experiment Dry-run
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** Bounded incentive/pricing policy with guardrails + an offline experiment dry-run.
- **Acceptance:** Price bounds enforced; elasticity from the versioned assumption set; guardrail
  audit (no price outside bounds, no negative-margin action); experiment labeled `simulated`
  (no real users → no causal lift claim).
- **Artifact:** `reports/v2/pricing/sensitivity.json` + `reports/v2/pricing/guardrail_audit.json`.
- **Command:** `make v2-pricing`. See `V2_PRICING.md`.
- **Delivered:** `ml/pricing/pricing_v2_eval.py` (bounded policy + guardrail audit, elasticity from
  assumptions, ledger objective) + `pricing_v2_run.py`. 576 seeded zone-hours: **0 guardrail
  violations**, safety zones base-fare, budget 0/40 respected, **negative control** catches a
  planted out-of-bounds surge; sensitivity grid (elasticity × surge-bound); **A/A switchback**
  effect ≈ 0, CI covers 0 (design valid). All `simulated`. Tests:
  `pytest tests/unit/test_v2_pricing.py` → 7 passed.

## V2-06 — GraphRAG Decision Copilot Benchmark
- **Status:** ✅ PASSED (2026-07-20)
- **Goal:** Copilot that answers operator questions via GraphRAG + typed tools; benchmark its
  correctness and retrieval relevance.
- **Acceptance:** Numeric answers rejected without a typed tool result; correctness and relevance
  scored against a fixed offline question set; every answer carries provenance.
- **Artifact:** `reports/v2/copilot/correctness_benchmark.json` + report md.
- **Command:** `make v2-copilot`. See `V2_GRAPHRAG_COPILOT.md`.
- **Delivered:** typed tools (`ml/copilot/tools.py`) + router/Copilot (`copilot.py`) + benchmark
  (`benchmark.py`). 15-Q fixed set: routing 1.0, correctness 1.0, refusal 1.0, grounded 1.0,
  **ungrounded_numeric=0, hallucinated=0 (hard gates pass)**. Numbers come only from typed tools
  reading committed V2 artifacts; router never produces numbers -> grounding guaranteed by design.
  Tests: `pytest tests/unit/test_v2_copilot.py` -> 7 passed.

## V2-07 — Operator Cockpit & Rider Preview
- **Status:** ✅ PASSED — artifact-backed metrics API + cockpit UI + rider preview, verified against the running app.
- **Goal:** Product UI where **every metric points to an artifact** (`run_id`/`artifact_id`),
  plus a rider-facing preview.
- **Acceptance:** No hard-coded UI metrics; each surfaced number resolves to a `reports/v2/**`
  artifact; demo heuristics only in `demo_fixture`; live/replay/research visually distinct.
- **Delivered:** `services/api/v2_metrics.py` (`cockpit_metrics()`) + endpoint
  `GET /v2/cockpit/metrics` — every headline metric (holdout WAPE, served model, profit lift, best
  policy, MPC regret, guardrail violations, LLM-news value) is read live from its committed
  `reports/v2/**` artifact and wrapped in the `ResultEnvelope`
  (`run_id`/`artifact_id`/`mode`/`claim_status`/`freshness`). `research` results are excluded from
  product surfaces (envelope-enforced); a missing artifact surfaces as a blocked envelope
  (`value=None`), never a fake number. 4 tests re-read each value from its artifact to guarantee no
  hard-coding (`tests/unit/test_v2_cockpit_metrics.py`).
- **Cockpit UI delivered:** `apps/web/app/cockpit/page.tsx` (+ `/cockpit` nav tab, typed client
  `api.cockpitMetrics`) renders each metric from `GET /v2/cockpit/metrics` with its **claim_status
  badge** (측정됨/시뮬레이션/…) and **artifact + run_id provenance**; no hard-coded numbers; a blocked
  metric shows "artifact 없음", never a fake value; `ModeBadge` marks the surface mode.
- **Verified end-to-end (both surfaces):** ran `make api` + `make web` (Next.js dev) and captured the
  real renders via headless Chromium:
  - **Operator cockpit** — `docs/screenshots/v2_cockpit.png`: all 7 metrics live from the API with
    claim badges (측정됨/시뮬레이션) + artifact/run_id provenance and the historical_replay mode badge.
    No hard-coded numbers on screen.
  - **Rider preview** — `docs/screenshots/v2_rider.png`: consumer view (`/`, rider role) with as-of
    availability, rider copilot (labeled 규칙 기반/rule-based), event-surge markers, and the
    historical_replay mode badge; demo/replay data, no fabricated live claims.
  - **Rider trip planner** — `docs/screenshots/v2_rider_trip.png`: "A에서 B까지" → walk → rent → bike
    → return → walk. `services/api/trip_planner.py` (`POST /v2/rider/plan-trip`) picks the nearest
    rentable/returnable station and lays out the legs with straight-line distances/times — **all
    numbers deterministic, never from an LLM**. The LLM's honest role (per V2-06): parse the NL
    request into origin/destination + narrate; rule-based here (`answer_mode`), LLM parser slots into
    `resolve_endpoints` when a key is configured. Verified live: "시청에서 뉴포트" → rent City Hall
    (6) → 🚲 5min/1173m → return Newport (10). 7 tests (`test_v2_trip_planner.py`).
    - **LLM-parse benchmark** (`ml/copilot/trip_parse_benchmark.py`, in `make v2-copilot`): the NL
      parse is the LLM seam. On a 10-query set (method-independent gold), rule-based scores **0.6**
      and the in-session LLM **1.0** — the LLM wins exactly the hard cases (typos `뉴포뜨`/`시쳥`,
      negation `익스체인지 말고`, origin-stated-last `출발은 시청`). LLM parses committed to
      `data/fixtures/v2/trip_parse_claude.jsonl` for audit; `offline_benchmark`. This is the V2-06
      lesson (intent understanding is the LLM's measured value) applied to the planner.
- **Status:** PASSED — artifact-backed metrics API + envelope enforcement + cockpit UI + rider
  preview, all verified against the running app.
- **Command:** `make web` (+ `make api`) driving V2 artifacts.

## V2-08 — Persistence, Monitoring & Delayed Labels
- **Status:** ✅ PASSED (drift = `blocked_data`, no live labels — stated honestly)
- **Goal:** Persist runs/artifacts; monitor served model; connect delayed live labels to close
  the `pending_live_label` → `measured` loop.
- **Acceptance:** Artifacts persisted with run manifests ✅; monitoring surfaces freshness ✅ (drift
  needs a live label stream → `blocked_data`, not faked); delayed-label backfill does not leak into
  past cutoffs ✅ (strict `available_at > forecast_cutoff` guard, unit-tested incl. the boundary).
- **Delivered:** `ml/monitoring/run_manifest.py` (indexes all 26 `reports/v2/**` artifacts w/ run_id,
  claim_status, freshness, staleness) + `ml/monitoring/delayed_labels.py` (leakage-safe
  pending→measured loop). Artifacts `reports/v2/monitoring/{run_manifest,delayed_labels}.json`.
  5 tests (`tests/unit/test_v2_monitoring.py`). See `V2_MONITORING.md`.
- **Command:** `make v2-monitor`.

## V2-09 — Final Audit & Portfolio Packaging
- **Status:** PLANNED
- **Goal:** Final honest audit; produce the claim matrix; package the V2 story.
- **Acceptance:** Every completion-rule artifact exists and is real; `V2_CLAIMS_MATRIX.md`
  filled from artifacts; `V2_KNOWN_LIMITATIONS.md` current; README/demo match implementation.
- **Artifact:** `reports/v2/final/claim_matrix.json` + `reports/v2/final/run_manifest.json`.
- **Command:** `make v2-audit` (final pass).

---

## Completion checklist (from the addendum)

- [ ] H3 holdout metrics — `reports/v2/holdout/`
- [ ] profit/regret ledger — `reports/v2/ledger/`
- [ ] LLM incremental value report — `reports/v2/llm_value/`
- [ ] MPC policy comparison — `reports/v2/mpc/`
- [ ] pricing sensitivity + guardrail audit — `reports/v2/pricing/`
- [ ] Copilot correctness benchmark — `reports/v2/copilot/`
- [ ] final claim matrix — `reports/v2/final/`

> `make` targets named above are **planned**, not yet implemented. Per the base contract, do not
> add a target until it can execute a meaningful, tested workflow.
