# V2-09 — Final Audit & Portfolio Packaging

_Phase: **V2-09**. Status: **PASSED — V2_COMPLETE**. Reproduce: `make v2-final` (exit 0 = pass)._
_Scope: judge the finished portfolio **by its committed artifacts** (addendum "Completion Rule").
This audit re-measures nothing — it reads `reports/v2/**` and enforces four machine-checkable gates.
The machine mirror is `reports/v2/final/claim_matrix.json`; the narrative matrix is
`docs/v2/V2_CLAIMS_MATRIX.md`; algorithm principles + metrics are in `docs/v2/V2_ALGORITHMS.md`._

---

## Gate results (machine-checked by `scripts/v2_final_audit.py`)

| # | Gate | Result | How it is checked |
|---|---|---|---|
| 1 | **Envelope honesty** — every committed V2 artifact carries the result-envelope fields and validates through `contracts.v2.ResultEnvelope` | **PASS** (31 artifacts) | constructs a `ResultEnvelope` per artifact; a mislabeled status (e.g. `research` outside research mode) or a `blocked_*` artifact carrying a value fails here |
| 2 | **Completion artifacts** — each artifact the completion rule requires is present | **PASS** | presence check for the 7 required artifacts |
| 3 | **Traceability** — each artifact's self-declared `artifact_id` path exists on disk | **PASS** | strips any `#pointer` and checks the file exists |
| 4 | **Claim matrix generated** | **PASS** | mirrors all artifacts + headline metrics into `claim_matrix.json` |

**Artifacts by claim_status:** `measured` 16 · `offline_benchmark` 7 · `simulated` 5 ·
`blocked_data` 1 · `demo_fixture` 1 · `research` 1  (total **31**).

---

## Completion-rule coverage (addendum)

| Required artifact | File | Headline (from the artifact) |
|---|---|---|
| H3 holdout metrics | `holdout/h3_multiholdout.json` | WAPE **0.4823**, MASE **0.821** (MASE<1 ⇒ beats seasonal-naive) |
| Profit/regret ledger | `ledger/profit_regret.json` | net **+$103,271** vs no-action; regret vs Oracle **$218,697** (`simulated`) |
| LLM incremental value report | `llm_value/incremental_value_borough.json` | structured lift **measured_improvement**; LLM-news **negative_lift**, net **−$17,789** |
| MPC policy comparison | `mpc/policy_comparison.json` | MPC total_cost **740.3**, regret **21.6** (best feasible) |
| Pricing sensitivity | `pricing/sensitivity.json` | A/A CI covers 0 (valid null design) |
| Pricing guardrail audit | `pricing/guardrail_audit.json` | **0** violations, budget respected |
| Copilot correctness benchmark | `copilot/correctness_benchmark.json` | routing **1.0**, hallucinations **0**, hard gates **pass** |
| Final claim matrix | `final/claim_matrix.json` | this run |

Supporting benchmarks also committed: GraphRAG relevance + neutral text-lookup control, RAGAS
retrieval + generation (faithfulness **1.0**, answer_relevancy **0.985**), trip-plan faithfulness
(**1.0**, 0 ungrounded), monitoring run-manifest + delayed-label loop.

---

## Honesty posture (what this portfolio does and does not claim)

- **Measured wins:** the promoted forecaster beats seasonal-naive on a rolling H3 multi-holdout;
  the **structured event feed** gives a measured accuracy lift; the Copilot routes to typed tools
  with **zero numeric hallucination**.
- **Honest null (headline finding):** **LLM-from-news features do not improve demand forecasting**
  on this data — reported with the LLM Feature Value metric + CI, root-caused (dense + precise-time
  + precise-location + forward-looking; news satisfies none), and bounded above by a *simulated*
  synthetic ceiling (+10.43%) that proves the method works when the source qualifies. See
  `docs/v2/V2_WHY_LLM_FEATURES.md`.
- **Simulated, not measured:** all dollar figures (ledger, MPC, pricing) are assumption-conditioned
  and labeled `simulated`; only unit counts are measured.
- **Research-only, excluded from the completion gate:** RL (tabular Q-learning + PPO) and QAOA. RL
  is scored on the same ledger for interest — **PPO 202.9 > tabular 247.8, both trail MPC 21.6; no
  RL advantage is claimed**. The `ResultEnvelope` validator blocks every research value from
  product surfaces.
- **Blocked, not faked:** the H3-grain graph test is `blocked_data` (events are borough-tagged, no
  lat/lng) — recorded, not fabricated.

---

## V2-09 acceptance checklist

- [x] Envelope honesty gate green over all 31 committed artifacts (`make v2-final` gate 1)
- [x] All 7 completion-rule artifacts present (gate 2)
- [x] Every artifact traceable to an on-disk path (gate 3)
- [x] `reports/v2/final/claim_matrix.json` regenerated from committed artifacts
- [x] `docs/v2/V2_ALGORITHMS.md` documents each algorithm's principle + metric
- [x] Unit tests: `tests/unit/test_v2_final_audit.py` (gates pass + mislabel is caught)

**V2-09 verdict: PASSED — V2_COMPLETE.** The completion rule is satisfied by committed artifacts;
RL/QAOA remain research-only and outside the gate.
