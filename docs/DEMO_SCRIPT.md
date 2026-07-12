# 90-Second Demo Script — the golden path

Everything below runs **entirely from fixtures, offline, no API key** (CLAUDE.md §3, §13, §17).
Historical Replay is the presentation mode. The forecast shown is a labelled demo heuristic
(`demo-heuristic-v1`), **not** the measured Phase 06 model — the two are kept distinct on purpose.

## Setup (once)

```bash
make install
make api      # terminal 1 — http://127.0.0.1:8000  (Demo Mode)
make web      # terminal 2 — http://localhost:3000   (needs `npm install` in apps/web first)
```

The replay window is 2026-07-12 12:00 → 18:00 (America/New_York). Two curated events cross it:
a **transit disruption** (Hoboken Terminal + City Hall) available at **14:00**, and a **large
venue event** (Newport) available at **15:00**.

## The walkthrough (~90 s)

1. **Alert — Control Tower.** Start at cutoff **13:59**. No events are available yet
   (`available_at ≤ cutoff`, §5.2); every zone's event-aware forecast equals its baseline, delta
   `0.00`. This is the "quiet" state.

2. **Advance to 14:00 → 14:30.** The transit event becomes available. It is extracted, lands in
   the graph, and its as-of graph features raise the event-exposure of the Hoboken/City Hall
   zones. Their forecasts move above baseline (positive delta). Advance again to **15:30** and the
   Newport venue event adds a third moved zone.

3. **Why — Why Changed.** Open a moved zone. The screen shows the full provenance chain
   `Article → Event → H3Zone → Feature`: the source article's evidence span, the extracted event
   (type, effect direction, severity, confidence), the concrete graph feature values it
   contributed, and the model-attributed forecast delta. Explanations are **never** evidence-free
   (§12, §13); "model-attributed", not "causal" (§4).

4. **Simulate — Scenario Lab.** Toggle the transit event **off**. The counterfactual forecast for
   its zones snaps back to the baseline (delta → 0), proving the delta is a transparent function
   of that event's graph exposure. Toggle it back on to restore the surge.

5. **Act — Rebalancing Planner.** With the events live (cutoff 15:30), the event zones are now in
   **deficit** (their targets were raised by the forecast surge). Solve the plan (MILP): bikes are
   moved from the surplus quiet-zone stations (Grove St, Exchange Place) into the three event
   zones. The plan lists each origin → destination move, the quantity, and distance; it passes an
   explicit **feasibility** check; and it reports the shortage reduction (8 → 0 units on the demo
   instance). Switch the method to **greedy** to compare — both feasible.

6. **(Optional) Research aside.** `make rebalance-demo` also runs the **Quantum Research Mode**
   QUBO for a single edge and prints "QUBO brute-force energy == exact enumeration energy → match".
   This is research only — a simulator, never hardware, with no quantum-advantage claim (§14.2).

## One-command backing check

```bash
make rebalance-demo
```

prints the greedy / MILP / exact-enumeration agreement and the QUBO validation, so the "Act" step
is reproducible without the UI.

## What is honest about this demo

- **Fixtures, not live.** News and station inventory are curated fixtures; live collectors are
  opt-in and off by default. Fixture data is never shown as live.
- **Demo heuristic, not the trained model.** The replay forecast is `demo-heuristic-v1`; the
  measured leaderboard lives in `README.md` / `docs/EVALUATION_PROTOCOL.md`.
- **Event lift is not a measured metric here.** On the June evaluation window the curated events
  postdate the trip data, so their measured forecast lift is null (`docs/KNOWN_LIMITATIONS.md`).
  The demo shows the *machinery* (extraction → graph → feature → delta → action) working as-of
  the cutoff, not a proven predictive gain.
