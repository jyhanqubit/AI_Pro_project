# V2-00 — Audit & Domain Correction

_Phase: **V2-00**. Status: **PASSED**. Reproduce: `make v2-audit` (exit 0 = pass)._
_Scope: reconcile the repo against `CLAUDE_V2_APPEND_REVISED.md`; correct domain drift; define
the result envelope; catalog stale numbers and their real source. This audit does **not**
re-measure any model — re-measurement is V2-01/V2-03._

---

## Gate results (machine-checked by `scripts/v2_audit.py`)

| # | Gate | Result | How it is checked |
|---|---|---|---|
| 1 | Domain correction — no Seoul/Gwanak/ParcelFlow/parcel-logistics drift in active code/docs | **PASS** (0 hits) | regex scan of `*.py/*.md/*.ts/*.tsx/*.yaml/*.json/*.toml`, excluding VCS/vendored dirs and V2 meta-docs that restate the prohibition |
| 2 | Result-envelope contract exists with the 9-value taxonomy + required fields | **PASS** | imports `contracts.v2.ResultEnvelope` + `ClaimStatus`, asserts fields and enum values |

---

## 1. Domain correction

The addendum requires the domain to stay **Citi Bike / New York City** (Station / H3 Zone /
Borough) and forbids inventing a Seoul / Gwanak / ParcelFlow / parcel-logistics contract.

- **Drift terms:** 0 occurrences in active code/docs. ✅
- **Actual geography in the repo** (case-insensitive token counts): `nyc` ~36.5k, `manhattan`
  ~13k+, `brooklyn` ~13k, `citibike/citi bike` ~236, `hoboken` ~105, `jersey city` ~30,
  `jc-202606` ~27.
- **Honest nuance (recorded, not a defect):** the v1 *measured* forecasting slice used the
  **Jersey City, NJ** Citi Bike system (`JC-202606` = June 2026), which is part of the Citi Bike
  network but is across the river from NYC proper. The product domain (Citi Bike, NYC-anchored)
  is correct; the measured-data footprint is currently JC/Hoboken plus NYC-wide permitted-events
  data. V2 docs must not upgrade "Jersey City slice" into an unqualified "NYC measured result".

**Disposition:** PASS. No correction edits needed; the JC vs NYC distinction is now documented
here and in `docs/v2/V2_KNOWN_LIMITATIONS.md`.

## 2. Result-envelope contract (defined this phase)

New in `contracts/v2/` (additive; nothing in v0/v1 contracts changed):

- `ClaimStatus` (`contracts/v2/enums.py`) — the mandated 9 values: `measured`,
  `offline_benchmark`, `simulated`, `pending_live_label`, `assumption`, `blocked_data`,
  `blocked_external`, `demo_fixture`, `research`.
- `ResultEnvelope` (`contracts/v2/envelope.py`) — carries `value`, `run_id`, `artifact_id`,
  `mode`, `claim_status`, `freshness`. It enforces the honesty rules in code:
  1. a `measured`/`offline_benchmark` value outside demo mode **must** cite an `artifact_id`;
  2. `demo_fixture` status only in `demo_fixture` mode;
  3. `research` status only in `research` mode;
  4. `blocked_*`/`pending_live_label` must carry **no** value (no fabricated number).
- `claimstate_to_status` — lossless-enough migration from the v1 `ClaimState` (5 → 9), so v1
  artifacts surface through the V2 envelope without breaking (`pending`→`pending_live_label`,
  `dry_run`→`simulated`).
- Tests: `tests/unit/test_v2_envelope.py` — **22 passed**.

## 3. Stale-number reconciliation

Per the addendum's source-of-truth order, **no number below may be quoted as a V2 claim** until a
current V2 command/artifact reproduces it. These are v1-era figures; they stay valid as *v1*
context but must be **re-measured under the H3 multi-holdout (V2-01)** before entering any V2
claim cell.

| Figure | Appears in | Reproduction command | Backing artifact | V2 disposition |
|---|---|---|---|---|
| Borough event lift WAPE 0.1013 → 0.0996 (−1.65%), CI [0.36, 5.11], `measured_improvement` | `docs/STATUS.md`, `docs/EVENT_LIFT_FINDINGS.md` | `python -m ml.forecasting.borough_event_lift` | `reports/borough_event_lift.json` | v1-measured (borough grain). Re-measure at **H3** grain + multi-holdout in V2-01/V2-03 before any V2 lift claim |
| Weather lift WAPE 0.4868 → 0.4893, `negative_lift` | `docs/STATUS.md` | `python -m ml.forecasting.weather_lift` | `reports/weather_lift.json` | v1-measured honest-negative. Weather not required in V2 MVP; keep as context |
| Forecasting M0 test WAPE 0.516 / MASE 0.794 vs B0 0.658 | `docs/STATUS.md`, `docs/V2_HANDOFF_REPORT.md` | evaluation run (needs `CITIBIKE_ZIP`) | run manifest | Re-measure under V2-01 multi-holdout; do not carry the single-split number into V2 |
| Retriever Recall@20 0.952 / E2E HitRate@3 0.754 | `docs/V2_HANDOFF_REPORT.md` | recommender eval targets | `reports/v1/recsys/*` | v1 recsys context; not on the V2 critical path |
| Event lift = 0 (`insufficient_event_overlap`) | `docs/V2_HANDOFF_REPORT.md` | V1-04 gate | — | **Key V2-03 driver**: re-evaluate once overlapping events exist; may stay `blocked_data` |

### Inconsistencies found (must be resolved by a live run, not by copying a doc)

1. **Test count disagrees across docs:** `114 passed`, `199 passed`, `200 passed`, and
   `204 passed` (all "+1 skipped") all appear in the doc set (`reports/v1/run_manifest.json`
   says baseline **115 passed / 1 skipped**). → The current suite count must be re-derived by
   running `pytest` in a provisioned env; no V2 doc should quote a fixed number until then.
2. **Legacy `v2-*` phase-number collision:** pre-addendum Makefile targets are labeled with
   phase numbers that clash with the addendum:
   - `v2-evaluate-predictive-lift` → "V2-02" vs addendum **V2-02 = Profit/Regret Ledger**
   - `v2-evaluate-search` → "V2-03" vs addendum **V2-03 = LLM Incremental Value Ablation**
   - `v2-evaluate-revenue` → "V2-05" vs addendum **V2-05 = Dynamic Pricing** (related, not identical)
   → The addendum (`CLAUDE_V2_APPEND_REVISED.md`) is the authoritative V2 phase map. These
   legacy targets are **real, working offline workflows** and are **not deleted**; a later phase
   should relabel them as `legacy` (or renumber) to remove the ambiguity. Recorded here so the
   collision is not mistaken for the addendum's phases.

## 4. Artifact inventory — reusable vs must re-measure

| v1 artifact | Reusable as-is in V2? | Note |
|---|---|---|
| `contracts/` + `contracts/v1/` | Yes (foundation) | V2 layers additively; `claimstate_to_status` bridges labels |
| `reports/borough_event_lift.json`, `reports/weather_lift.json` | As v1 context only | Not a V2 claim until re-measured at H3 grain |
| Offline fixtures (`data/fixtures/*`) | Yes | Feed V2 offline runs; V2 fixtures go under `data/fixtures/v2/` |
| Forecasting/recsys/pricing code (`ml/*`, `config/*_v2.py`) | Yes as building blocks | Must be driven through the V2 multi-holdout + ledger before claims |
| v1 test suite | Yes | Re-run to establish the current green count (see inconsistency #1) |

## 5. V2-00 acceptance checklist

- [x] No Seoul/ParcelFlow/parcel drift in active code/docs (`make v2-audit` gate 1)
- [x] `claim_status` result envelope defined in `contracts/v2/` (gate 2) + 22 unit tests green
- [x] Stale-number audit lists every headline figure and its real source/disposition
- [x] Artifact produced: this file + `make v2-audit` runnable check
- [x] Two live inconsistencies recorded (test count, legacy phase-number collision)

**V2-00 verdict: PASSED.** Next input contract → **V2-01** (Measured Model Productization &
H3 Multi-Holdout): promote a measured model artifact and evaluate it across ≥3 rolling H3
holdout windows; every headline number in §3 above is re-measured there before it may enter the
claim matrix.
