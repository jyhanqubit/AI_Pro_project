# ShockFlow AI — Session Handoff

Handoff for continuing work in a new session (e.g. claude.ai/code on the web). Read this, then
read **CLAUDE.md** (the operating contract) before changing anything.

_Last updated: 2026-07-13. Latest pushed commit: `4993652` (Phase 07 UI). Branch: `master`._

---

## 1. Quick facts

| | |
|---|---|
| Repo | `jyhanqubit/AI_Pro_project` (GitHub, private) |
| Branch | `master` (HEAD == origin/master == `4993652`) |
| Phases complete & pushed | **00–07** (contracts → collection → demand features → LLM events → graph → as-of graph features → forecasting/eval → API+UI) |
| Phases remaining | **08** (Rebalancing & Quantum Research), **09** (Final Audit & Portfolio Packaging) |
| Python gate | `ruff check .` ✓, `ruff format --check .` ✓, `mypy .` ✓, `pytest` → **101 passed** |
| Local env | Windows, `.venv` = Python 3.12.10 (repo pins `>=3.11`) |
| Hosted mobile demo | https://claude.ai/code/artifact/76ef6958-41e7-440a-b9ac-15201bc75320 |

---

## 2. Environment setup (fresh clone)

```bash
# POSIX (web / Linux / mac): use .venv/bin
python -m venv .venv
.venv/bin/pip install -e ".[dev,ml,api]"
# Windows: use .venv/Scripts instead of .venv/bin
```

Gate (all must pass before any commit):

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy .
.venv/bin/pytest            # expect 101 passed
```

Useful `make` targets: `install lint typecheck test collect-demo build-features
extract-events-demo graph-upsert-demo graph-features-demo train-baseline evaluate api web`.

**Data note:** the real Citi Bike June-2026 zip lives at
`data/raw/citibike/JC-202606-citibike-tripdata.csv.zip` but is **git-ignored — it is NOT in a
fresh clone.** It is only needed for `make evaluate` (Phase 06), which is already done; its
measured results are in the README and `reports/` (also git-ignored, regenerable). Phases 08–09
do **not** need it. Do not commit large raw data.

---

## 3. What is complete (per phase)

- **00–05** — Pydantic contracts (`contracts/`), collectors (`pipelines/collectors/`), demand
  aggregation + leakage-safe features (`pipelines/features/`), mock LLM event extraction
  (`pipelines/events/`), offline event graph (`pipelines/graph/`), as-of graph features. Real
  June-2026 data validated end-to-end offline.
- **06 — Forecasting/tuning/eval** (`ml/forecasting/`, `config/forecasting.py`): seasonal-naive
  B0, six-algorithm zoo, rolling-origin CV, GridSearch, permutation-importance feature selection,
  B0–B4 ablation, metrics (WAPE/MAE/MASE/event-window/peak-dir/delta-stability) **plus a
  data/domain-customised metric OCS** (asymmetric shortage-vs-overflow, reduces to WAPE at equal
  costs). Results & interpretation are in README + `docs/EVALUATION_PROTOCOL.md`. Honest finding:
  event features are zero on the June window (curated events postdate the data, §5.2), so B2–B4 =
  B1; and OCS reorders the leaderboard (knn wins CV-WAPE but is worst learned model on OCS).
- **07 — API + UI**:
  - `services/api/` — FastAPI replay service, offline. Endpoints: `/v1/health`,
    `/v1/replay/state`, `/v1/replay/set-cutoff`, `/v1/events`, `/v1/forecasts`,
    `/v1/zones/{id}/explanation`, `/v1/scenarios`. `/v1/rebalancing/solve` currently returns
    **501** (deferred to Phase 08 — do NOT fake it). 7 integration tests pass. `make api`.
  - `apps/web/` — Next.js (App Router, TS strict) operator console: Control Tower, Why Changed,
    Scenario Lab, Rebalancing (honest placeholder). Consumes the API. `make web`.

---

## 4. Hosted mobile demo (already live)

A self-contained snapshot of the console with **real pipeline data** baked in (computed by the
actual `ReplayEngine` at every cutoff) is hosted as an Artifact:
**https://claude.ai/code/artifact/76ef6958-41e7-440a-b9ac-15201bc75320**

- Open on mobile in a browser **logged into the same claude.ai account**. It won't appear in the
  Claude mobile app's normal artifact list — use the URL. It is **private by default**; use the
  page's Share menu to share.
- Regenerate/update it (NOT in the repo — lives in the session scratchpad):
  `scratchpad/console_template.html` (hand-written UI) + `scratchpad/export_demo.py`
  (dumps real ReplayEngine states into the template → `console.html`). Re-run the exporter, then
  re-publish the **same file path** to keep the URL. If continuing in a different session, you may
  need to re-create these two files (they were not committed).

---

## 5. IN FLIGHT — remote Phase 08/09 agent (VERIFY BEFORE REDOING)

A background/remote agent was launched to do Phases 08 and 09. **As of this handoff it has NOT
pushed anything** — `origin/master` is still `4993652`. Before starting Phase 08/09 yourself:

```bash
git fetch origin && git log origin/master --oneline -8
```

- If new `Phase 08` / `Phase 09` commits appear on `origin/master`: pull them, review against
  CLAUDE.md, run the gate, and only fill gaps.
- If nothing new appears (likely, if the remote env lacked push credentials or was tied to the
  closed local session): **do Phases 08–09 yourself** per section 6. Do not assume the remote
  work landed.

---

## 6. Remaining work

### Phase 07 wrap-up (small)
- Verify the UI compiles under TS strict: in `apps/web`, `npm install` then `npm run typecheck`
  and `npm run build`; fix any strict-mode type errors. (Node/npm required; if unavailable,
  document that the UI build was not verified.)
- Add `docs/DEMO_SCRIPT.md` — the 90-second golden path: cutoff 13:59 (no event) → advance to
  14:00/14:30 (transit event appears, zones shift) → Why Changed (evidence + trace + delta) →
  Scenario Lab (toggle event off reverts the delta) → note rebalancing is Phase 08.

### Phase 08 — Rebalancing & Quantum Research (CLAUDE.md §14)
Implement in `optimization/classical/` and `optimization/quantum/` (currently empty scaffolds).
Build order:
1. `config/rebalancing.py` — cost weights (shortage, overflow, distance, capacity penalty).
2. `optimization/classical/objective.py` — pure cost function over a plan.
3. `optimization/classical/feasibility.py` — explicit checks: can't move more than origin has;
   can't exceed destination capacity; non-negative integers; respect vehicle/total-move limit;
   report infeasibility explicitly.
4. `optimization/classical/greedy.py` — greedy feasible baseline (always feasible).
5. `optimization/classical/milp.py` — exact constrained solver. **`scipy.optimize.milp` is
   available** (scipy 1.18 installed) — use it; fall back to exact enumeration for tiny instances.
6. `optimization/quantum/qubo.py` — small QUBO with documented variable mapping; **assert the
   QUBO optimum equals the classical constrained optimum via exact enumeration** (required).
7. `optimization/quantum/qaoa.py` — OPTIONAL, lazy `qiskit` import; if absent, expose an
   "unavailable" path and skip its tests with a documented reason. Label **Quantum Research
   Mode**; never claim advantage; never present simulator output as hardware.
8. Wire the API: replace the 501 in `services/api/app.py` `/v1/rebalancing/solve` with a real
   handler returning a typed plan (origin, destination, moved qty, distance/cost, feasibility,
   shortage/overflow reduction). Add request/response schemas in `services/api/schemas.py`. Derive
   inventory/shortage from the GBFS station-status fixture (`data/fixtures/gbfs_station_status.json`)
   and/or a small curated rebalancing fixture. Update `apps/web/app/rebalancing/page.tsx` to render
   the plan.
9. Tests (unit + integration): greedy always feasible; MILP optimal / matches enumeration;
   feasibility rejects bad moves; QUBO == enumeration; API returns a feasible plan.
10. Docs: `docs/OPTIMIZATION.md`; update README, STATUS, KNOWN_LIMITATIONS. Gate → commit → push.

### Phase 09 — Final Audit & Portfolio Packaging (CLAUDE.md §18, §23)
- Sync docs to the implementation: create/update `docs/PRD.md`, `docs/ARCHITECTURE.md`,
  `docs/DATA_CONTRACTS.md`, `docs/GRAPH_SCHEMA.md`, `docs/EVALUATION_PROTOCOL.md` (exists),
  `docs/DEMO_SCRIPT.md`, `docs/KNOWN_LIMITATIONS.md` (exists), `docs/STATUS.md`, `README.md`.
- `docs/STATUS.md` must state: completed phase (09), commands verified, tests passing/failing,
  measured results available, known blockers, portfolio-ready.
- Final honesty audit: no fabricated metrics, no causal claims from feature attribution, no
  quantum-advantage claims, event-lift limitation stated, fixture vs live vs measured clearly
  separated. Full gate must be green. Commit → push.

---

## 7. Critical cautions (do not violate)

- **Follow CLAUDE.md exactly.** It overrides defaults.
- **Temporal correctness:** `available_at = max(published_at, first_seen_at)`; use an event only
  when `available_at <= forecast_cutoff`; no future data; no random K-fold (rolling-origin only);
  never weaken the leakage tests (esp. `tests/unit/test_graph_features.py` 14:01→14:00).
- **No fabrication:** no invented metrics, news content, model results, or API responses. If
  event features don't help, say so (they don't, on the June window — that is already documented).
- **Demo forecaster labeling:** the API/UI forecast is a **labelled demo heuristic
  (`demo-heuristic-v1`, Historical Replay)** — NOT the measured Phase 06 model. Keep them
  distinct; never present the demo number as the trained/measured result.
- **Quantum:** label Quantum Research Mode; no advantage claims; simulator ≠ hardware; validate
  QUBO against exact enumeration; skip QAOA tests with a reason if qiskit is absent.
- **Don't** commit the June zip / `reports/**` / `.venv` / `node_modules` (already git-ignored).
- **Don't** weaken/skip failing tests to pass a phase. Fix the cause or document a real
  environment skip.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Don't
  force-push. Only commit when the gate is green.

---

## 8. Key file map

```
CLAUDE.md                         operating contract (read first)
README.md                         product story + Phase 06 results/interpretation (Korean)
docs/STATUS.md                    phase status, verified commands, results, blockers
docs/EVALUATION_PROTOCOL.md       forecasting eval method + metrics (incl. OCS)
docs/KNOWN_LIMITATIONS.md         honest scope boundaries (esp. event-lift caveat)
contracts/                        Pydantic v2 data contracts (§6)
config/                           typed config: features, events, graph_features, forecasting, api
pipelines/features/               demand aggregation + leakage-safe + as-of graph features
ml/forecasting/                   baselines, model zoo, splits, metrics(+OCS), experiment, run
services/api/                     FastAPI replay service (app, replay, schemas, forecaster)
apps/web/                         Next.js operator console (4 screens)
optimization/classical|quantum/   EMPTY — Phase 08 target
tests/unit, tests/integration     101 passing
```
