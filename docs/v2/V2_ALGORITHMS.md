# V2 Algorithms — Principles & Metrics

A single reference for **how each algorithm works** and **how it is measured**. Every metric here
is defined in code and every headline number is reproduced by a committed artifact under
`reports/v2/**` (the final claim matrix in `reports/v2/final/claim_matrix.json` links each claim to
its artifact). Formulas match the implementations in `ml/forecasting/metrics.py`,
`ml/forecasting/llm_feature_value.py`, `optimization/`, and `ml/copilot/`.

Contents:
1. Shared forecasting metrics (WAPE / MAE / MASE / OCS)
2. Demand forecasting models (Seasonal-Naive → HistGradientBoosting; the A0/A1/A2 ablation)
3. LLM Feature Value — did the LLM features improve accuracy?
4. Profit / Regret ledger
5. Rebalancing decisioning — No-Action / Greedy / MILP / MPC / Oracle
6. Reinforcement learning (research) — tabular Q-learning & PPO
7. Dynamic pricing (simulated)
8. Decision Copilot — typed-tool grounding, GraphRAG retrieval, RAGAS

---

## 1. Shared forecasting metrics

All error metrics are on the **H3 zone × local-hour** grain, over an as-of holdout (no leakage).

| Metric | Formula | Why | Zero-denominator rule |
|---|---|---|---|
| **MAE** | `mean(|y − ŷ|)` | absolute scale, in bikes | `NaN` if empty |
| **WAPE** | `Σ|y − ŷ| / Σ|y|` | scale-free, robust to per-cell zeros (sparse zones) | `0` if error also 0, else `NaN` |
| **MASE** | `MAE(model) / MAE(seasonal-naive, in-sample)` | skill *relative to the naive* — `<1` beats naive | `NaN` if scale 0/NaN |
| **OCS** | `(c_short·under + c_over·over) / Σy` | asymmetric operational cost (stockout ≠ overflow) | same as WAPE; equals WAPE when `c_short=c_over` |

- **MASE scale** is the in-sample MAE of the seasonal-naive (`y_t` vs `y_{t−period}`), `period = 168 h`
  (weekly). Computed on the **training** history only (`seasonal_naive_scale`).
- WAPE is the **headline** because demand is sparse and heavy-tailed; a per-cell MAPE would divide
  by near-zero cells. See `ml/forecasting/metrics.py`.

---

## 2. Demand forecasting models

**Principle — build in strict order of complexity, gate each step on leakage tests** (base
contract §11.1). The LLM never predicts demand directly; it only produces *features*.

| Model | Principle | Role |
|---|---|---|
| **B0 Seasonal-Naive** | `ŷ_t = y_{t−168h}` (same hour last week) | the honesty floor; also the MASE denominator |
| **Global tree (promoted)** | `HistGradientBoosting` on lag/rolling/calendar features, one global model over all zones | the served model |
| **Event-aware** | the tree + LLM/graph event features (§3) | the thing under test |

**Promoted model** (`reports/v2/holdout/promoted_model.json`): `hist_gradient_boosting`,
`lr=0.05, depth=8, iters=600`. Promotion = the config that won the H3 multi-holdout; it is the
artifact the non-demo API serves (`ml/forecasting/promoted.py`), never a demo heuristic.

**H3 multi-holdout** (`reports/v2/holdout/h3_multiholdout.json`): **rolling-origin** evaluation over
**3 expanding windows** (never random K-fold — that would leak the future). Each window trains up to
a cutoff and tests the next block. Measured: **WAPE 0.4828 ± 0.0030, MASE 0.7996 ± 0.0186**
(MASE < 1 ⇒ beats seasonal-naive; naive ≈ 0.648 WAPE).

**Feature ablation** (the venue for §3):

```
A0  demand history + calendar          (no events)
A1  A0 + structured event feed (permits, counts)
A2  A1 + LLM-from-news event features
```

Every ablation rung uses **identical cutoffs and split windows** (contract §5.4) so a WAPE delta is
attributable to the added feature, not to a different split.

---

## 3. LLM Feature Value (LFV) — the decision metric

**Question it answers:** *did adding a feature layer meaningfully improve forecast accuracy?* —
as a reproducible verdict, not a vibe. Defined in `ml/forecasting/llm_feature_value.py`.

**Principle:**
1. Compute WAPE **only on the LLM-active subset** (zone-hours where the feature actually fires).
   Diluting the delta across millions of inactive cells would hide any real effect.
   `skill = (WAPE_without − WAPE_with) / WAPE_without` (relative WAPE reduction, `+` = better).
2. **Block-bootstrap** the active subset (contiguous time blocks, preserving autocorrelation) to get
   a 95% CI on the skill.
3. **Decision rule (pre-declared, not tuned):** the effect must clear BOTH gates —
   `|skill| ≥ rel_threshold (0.01)` **AND** the CI must exclude 0 — else it is a null.

```
skill ≥ +0.01 and CI>0   → MEANINGFUL_POSITIVE
skill ≤ −0.01 and CI<0   → MEANINGFUL_NEGATIVE
otherwise                → NO_MEANINGFUL_EFFECT
(active support < min_active=100)  → INSUFFICIENT_SUPPORT
```

**Metric = the tuple `(decision, skill, CI, n_active)`.** It reports a null as readily as a win — a
non-improving model is a first-class, honest outcome (contract §11.4). Pure function, 6 unit tests.

**What it measured (the core V2-03 finding):**
- Structured event feed (A1−A0): **`MEANINGFUL_POSITIVE +2.69%`** at nowcast — events help.
- LLM-from-news (A2−A1): net **negative / null** — news is redundant vs the structured feed.
- Root cause (proven, not assumed): a feature helps only when its source is **dense +
  precise-time + precise-location + forward-looking**; news satisfies none (only 2/23 events are
  forward-looking). Synthetic ceiling (`synthetic_ceiling.json`, *simulated*) injects sources that
  meet all four → **+10.43%**, proving the *method* works and the real-news null is a **source**
  limitation. Full write-up: `docs/v2/V2_WHY_LLM_FEATURES.md`.

---

## 4. Profit / Regret ledger

**Principle** (`optimization/ledger.py`, contracts in `contracts/v2/ledger.py`): translate a
forecast's accuracy into money through a **versioned assumption set** (`config/v2/assumptions.yaml`).

```
contribution_margin = margin_per_rental · realized_rentals
shortage_cost       = shortage_externality · unmet_demand_units      (externality, NOT lost margin)
overflow_cost       = overflow_penalty · overflow_units
relocation_cost     = reposition_cost_per_unit · moved_units
net = contribution_margin − shortage_cost − overflow_cost − relocation_cost
regret_vs_oracle = Oracle_net − policy_net        (≥ 0 by construction)
```

**Integrity rules:** margin counts only *realized* rentals; shortage is the **externality** on unmet
demand and is **not** double-counted as lost margin; every dollar term is `claim_status: simulated`
(assumption-conditioned), only the unit counts are `measured`. A **sensitivity sweep** over the
assumption grid must keep the sign stable before any dollar claim.

**Metric:** `net` (higher better) and `regret_vs_oracle` (lower better).
Measured (`reports/v2/ledger/profit_regret.json`): promoted forecast nets **+$103,271** vs
seasonal-naive over 114,079 zone-hours; **sign positive across all 9 cost settings**.

---

## 5. Rebalancing decisioning — the policy scoreboard

All policies are scored on the **same** V2-02 ledger over one seeded commute scenario, with the same
feasibility solver. **Oracle** uses realized demand as an offline **upper bound**, so every policy's
`regret_vs_oracle ≥ 0`. Artifact: `reports/v2/mpc/policy_comparison.json` (`simulated`).

| Policy | Principle |
|---|---|
| **No-Action** | never move — the do-nothing floor |
| **Greedy** | each hour, move from the most-overfull to the most-empty zone until locally balanced |
| **MILP** (single-period) | mixed-integer program: minimize this hour's ledger cost s.t. capacity + vehicle limits + non-negative integer moves |
| **MPC** | receding horizon: set each zone's target from an **H-step forecast** `target = clip(cap/2 − Σ_H forecast_net, 0, cap)`, solve the same MILP toward it, execute one step, repeat |
| **Oracle** | the MILP with the *realized* demand substituted for the forecast — an offline bound, not a deployable policy |

**Required constraints (all enforced, infeasibility reported explicitly):** can't move more than a
zone holds, can't exceed destination capacity, non-negative integer moves, respect vehicle capacity.

**Metric:** ledger `total_cost` (lower better) and `regret_vs_oracle`.
Measured: NoAction 1127 / Greedy 1155 / MILP 1087 / **MPC 740** / Oracle 719 → **MPC best feasible,
regret 21.6 (~3% of Oracle)**, all feasible.

---

## 6. Reinforcement learning (Research Mode only)

RL is **research-only** and **not** a V2 completion condition (addendum). It adds a *learned-control*
baseline to the §5 scoreboard, measured on the identical ledger + eval scenario. **No RL advantage is
claimed** (mirrors the "no quantum advantage" rule). Full doc: `docs/v2/V2_RESEARCH_RL.md`.
Both learners are **pure numpy** (no torch), fully seeded, and offline (no online/bandit learning).

### 6a. Tabular Q-learning (`optimization/rl/qlearning.py`)

**Principle — model-free value iteration on sampled transitions.** Learn `Q(s,a)` = expected future
(negative) cost, via the temporal-difference update

```
Q(s,a) ← Q(s,a) + α · [ r + γ · max_a' Q(s',a') − Q(s,a) ]
```

with ε-greedy exploration (linear decay). The greedy policy is `argmax_a Q(s,a)`.
- **State** (72): `(hour_of_day, system_imbalance_bucket ∈ {−,0,+})` — coarse, *global*.
- **Action** (15): a *global* target-shaping control `(α ∈ {0..2}, H ∈ {1,3,6})`. This subsumes the
  built-in policies — `α=0` = No-Action, **`α=1,H=6` = MPC** — so MPC is one of its own actions.

### 6b. PPO (`optimization/rl/ppo.py`)

**Principle — policy-gradient with a trust region.** Directly optimize a stochastic policy
`π_θ(a|s)` (a diagonal-Gaussian MLP; actions clipped to `[0,1]`) by ascending the **clipped
surrogate**:

```
r_t(θ) = π_θ(a_t|s_t) / π_θ_old(a_t|s_t)
L = E[ min( r_t · Â_t ,  clip(r_t, 1−ε, 1+ε) · Â_t ) ]  +  entropy bonus  −  value loss
```

- Advantages `Â_t` via **GAE(λ)**: `δ_t = r_t + γV(s_{t+1}) − V(s_t)`, `Â_t = Σ (γλ)^l δ_{t+l}`.
- A separate MLP **critic** `V(s)` trained by MSE to the returns; **Adam** on all params
  (manual backprop).
- **State** (`2·z+2`): **per-zone** `[inventory/cap, Σ_H forecast/cap]` + clock — the information
  MPC uses. **Action**: **per-zone** continuous target fraction. This removes the tabular
  state/action bottleneck.

### Metric & result (`reports/v2/research/rl_rebalancing.json`)

Same as §5: ledger `total_cost` / `regret_vs_oracle` on the held-out `seed=42` scenario, with
**training on disjoint seeds** (the eval noise is never trained on — same leakage discipline as the
forecaster). Verdict fields: `best_rl`, `ppo_beats_tabular`, `beats_mpc`.

| policy | regret vs Oracle |
|---|---:|
| oracle | 0.0 |
| **mpc** | **21.6** |
| rl_ppo | 202.9 |
| rl_qlearning | 247.8 |
| milp / no_action / greedy | 368 / 408 / 436 |

**Reading:** PPO (richer representation) beats tabular Q-learning (202.9 < 247.8) — confirming the
score was capped by *representation*, not the algorithm. Both trail MPC, because MPC's gap to Oracle
is **mostly irreducible forecast noise** (Oracle sees realized demand; a learner cannot). No RL
advantage claimed.

---

## 7. Dynamic pricing (simulated)

**Principle** (`ml/pricing/`, doc `docs/v2/V2_PRICING.md`): a **bounded** surge/discount on top of a
safe base fare, driven by forecast imbalance, with hard **guardrails** (max multiplier, budget cap,
protected floor) and an **A/A dry-run** to validate the experiment design before any live test.
Elasticity is a **versioned assumption**; all quotes are **shadow** (never charged).

**Metric** (`reports/v2/pricing/{sensitivity,guardrail_audit}.json`, `simulated`): guardrail-violation
count (must be **0**), budget adherence, a **negative-control** that must pass, and an **A/A CI that
covers 0** (a valid null design). Measured: **0 violations over 576 zone-hours**, negative control
passes, A/A CI covers 0.

---

## 8. Decision Copilot — grounding & retrieval

The LLM is used **only** for event structuring, tool routing, and explanation — **never** to compute
a number. A numeric answer with no typed tool result behind it is rejected (addendum "LLM
Boundaries"). Doc: `docs/v2/V2_GRAPHRAG_COPILOT.md`.

| Component | Principle | Metric | Result |
|---|---|---|---|
| **Typed-tool routing** | NL question → a typed tool call → the tool's numeric result is the only source of numbers | routing accuracy + **numeric-hallucination count** | 20 Q: real-Claude routing **1.0/1.0/1.0**, **halluc = 0** (keyword baseline hallucinates 3 → fails) |
| **GraphRAG retrieval** | retrieve evidence events from the as-of event graph; answer cites them | precision / recall vs a gold set | on a *graph-structural* task GraphRAG 21/21, but that is high **by construction** |
| **Neutral text-lookup control** | method-independent gold, plain text retrieval | top-1 accuracy | flat_text **0.833 beats** graph_boosted 0.750 — degree-boost gives **no** lift on text; *match the tool to the query type* |
| **RAGAS retrieval** | real `ragas` 0.4.3 **non-LLM** metrics | context-precision / recall | flat 0.833 vs graph 0.771 (recall tied) — agrees with the control |
| **RAGAS generation** | faithfulness = every answer claim is grounded in retrieved context; answer-relevancy | faithfulness / answer_relevancy | **faithfulness 1.0**, **answer_relevancy 0.985** over 10 answered Q (judged in-session; verdicts committed + drift-guarded) |
| **Trip-plan faithfulness** | rider plan numbers (distance/time) must be exactly the ones in the typed plan | grounded-number ratio | **1.0**, 0 ungrounded; negative control ("999") caught |

**Honest framing:** GraphRAG is not universally better — it wins only when the query is graph-shaped.
The neutral control + RAGAS bound the verdict both ways, which is the point.

---

## Where each algorithm may appear (mode / claim discipline)

| Algorithm | claim_status | Product surface? |
|---|---|---|
| Promoted forecaster, H3 holdout, LFV, structured-event lift | `measured` | yes (non-demo) |
| Copilot benchmarks, trip faithfulness | `offline_benchmark` | yes (offline) |
| Ledger, MPC, pricing | `simulated` | comparison only, labeled |
| Synthetic ceiling | `simulated` | research/analysis only |
| **RL (Q-learning, PPO)** | `research` | **never** — blocked by `ResultEnvelope` |

The `ResultEnvelope` validator (`contracts/v2/envelope.py`) enforces this in code; the final audit
(`make v2-final`) re-verifies every committed artifact against it.
