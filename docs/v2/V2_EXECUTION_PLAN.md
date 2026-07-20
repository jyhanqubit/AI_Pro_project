# V2 Execution Plan — Phases V2-00 … V2-09

Each phase below lists **goal · acceptance criteria · completion artifact · reproduction command**.
Phase gates are honored: do not advance until acceptance criteria are met, relevant tests pass,
docs reflect actual behavior, and outputs are real. `Status` starts at `PLANNED` for every phase;
update it only from an executed command or a committed artifact.

Legend for `Status`: `PLANNED` → `IN_PROGRESS` → `PASSED` / `PASSED_BLOCKED_*` / `BLOCKED`.

---

## V2-00 — Audit & Domain Correction
- **Status:** PLANNED
- **Goal:** Reconcile repo against V2 addendum; confirm domain is Citi Bike / NYC everywhere;
  inventory which v1 artifacts are re-usable vs must be re-measured; define the result envelope.
- **Acceptance:** No Seoul/ParcelFlow/parcel references in active code/docs; `claim_status`
  envelope defined in `contracts/v2/`; stale-number audit lists every doc figure and its source.
- **Artifact:** `reports/v2/final/v2_audit.md` (audit table) + envelope contract committed.
- **Command:** `make v2-audit` _(target to be added when it runs a real check)_.

## V2-01 — Measured Model Productization & H3 Multi-Holdout
- **Status:** PLANNED
- **Goal:** Promote a measured forecasting model artifact and serve it in non-demo modes;
  evaluate it across multiple rolling H3 holdout windows (not a single split).
- **Acceptance:** Promoted model manifest referenced by the API; ≥3 rolling-origin holdout
  windows with WAPE/MAE/MASE reported per window and aggregated; no random split; leakage tests pass.
- **Artifact:** `reports/v2/holdout/h3_multiholdout.json` + `reports/v2/holdout/README.md`.
- **Command:** `make v2-holdout`. See `V2_EVALUATION_PROTOCOL.md`.

## V2-02 — Profit / Regret Ledger
- **Status:** PLANNED
- **Goal:** Translate forecast error into money: expected shortage cost, overflow cost,
  relocation cost, and regret vs Oracle upper bound.
- **Acceptance:** Contribution margin and shortage externality kept separate; no double-count of
  lost margin; assumptions loaded from a versioned `config/v2/` assumption set; Oracle labeled as
  offline upper bound.
- **Artifact:** `reports/v2/ledger/profit_regret.json` + `reports/v2/ledger/README.md`.
- **Command:** `make v2-ledger`. See `V2_PROFIT_REGRET_LEDGER.md`.

## V2-03 — LLM Incremental Value Ablation
- **Status:** PLANNED
- **Goal:** Separate **No-Event**, **Rule-Event**, and **LLM-Event** feature sets and measure the
  incremental predictive lift and the incremental profit of each — net of LLM cost.
- **Acceptance:** Three ablation arms share identical cutoffs/splits; lift reported with a CI;
  LLM incremental token/$ cost included; honest reporting if LLM adds no lift over the rule arm.
- **Artifact:** `reports/v2/llm_value/incremental_value.json` + report md.
- **Command:** `make v2-llm-value`. See `V2_LLM_VALUE_ABLATION.md`.

## V2-04 — Multi-period MPC Decisioning
- **Status:** PLANNED
- **Goal:** Compare the four mandatory policies over a multi-period horizon on the ledger objective.
- **Acceptance:** `No Action`, `Greedy`, `Single-period MILP`, `MPC` all run on the same
  instances; every plan feasibility-checked; infeasibility reported explicitly; MPC uses the
  forecast horizon, not future truth.
- **Artifact:** `reports/v2/mpc/policy_comparison.json` + report md.
- **Command:** `make v2-mpc`. See `V2_MPC_DECISIONING.md`.

## V2-05 — Dynamic Pricing & Experiment Dry-run
- **Status:** PLANNED
- **Goal:** Bounded incentive/pricing policy with guardrails + an offline experiment dry-run.
- **Acceptance:** Price bounds enforced; elasticity from the versioned assumption set; guardrail
  audit (no price outside bounds, no negative-margin action); experiment labeled `simulated`
  (no real users → no causal lift claim).
- **Artifact:** `reports/v2/pricing/sensitivity.json` + `reports/v2/pricing/guardrail_audit.json`.
- **Command:** `make v2-pricing`. See `V2_PRICING.md`.

## V2-06 — GraphRAG Decision Copilot Benchmark
- **Status:** PLANNED
- **Goal:** Copilot that answers operator questions via GraphRAG + typed tools; benchmark its
  correctness and retrieval relevance.
- **Acceptance:** Numeric answers rejected without a typed tool result; correctness and relevance
  scored against a fixed offline question set; every answer carries provenance.
- **Artifact:** `reports/v2/copilot/correctness_benchmark.json` + report md.
- **Command:** `make v2-copilot`. See `V2_GRAPHRAG_COPILOT.md`.

## V2-07 — Operator Cockpit & Rider Preview
- **Status:** PLANNED
- **Goal:** Product UI where **every metric points to an artifact** (`run_id`/`artifact_id`),
  plus a rider-facing preview.
- **Acceptance:** No hard-coded UI metrics; each surfaced number resolves to a `reports/v2/**`
  artifact; demo heuristics only in `demo_fixture`; live/replay/research visually distinct.
- **Artifact:** UI wired to artifact IDs; screenshot set under `docs/screenshots/`.
- **Command:** `make web` (+ `make api`) driving V2 artifacts.

## V2-08 — Persistence, Monitoring & Delayed Labels
- **Status:** PLANNED
- **Goal:** Persist runs/artifacts; monitor served model; connect delayed live labels to close
  the `pending_live_label` → `measured` loop.
- **Acceptance:** Artifacts persisted with run manifests; monitoring surfaces freshness/drift;
  delayed-label backfill does not leak into past cutoffs.
- **Artifact:** run manifests under `reports/v2/**`; monitoring doc.
- **Command:** `make v2-monitor` _(added when real)_.

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
