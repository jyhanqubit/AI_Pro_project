# V2 Known Limitations

Honest scope boundaries for V2. Updated at V2-09 from real state. Complements
`../KNOWN_LIMITATIONS.md` (v1).

## Current status

V2 is at **kickoff / scaffolding** (docs + folders only). No V2 phase has produced a measured
artifact yet, so every result in the V2 docs is `pending`. Nothing in `reports/v2/**` should be
read as a measured claim until its owning phase runs.

## Known / expected limitations

- **Event overlap (carried from v1):** v1 found `insufficient_event_overlap` — curated events
  fell outside the June evaluation window, so LLM event lift measured 0. V2-03 depends on
  sufficient real event overlap; if collection stays blocked, the LLM-vs-rule result may remain
  `blocked_data` and must be reported as such, not faked.
- **External collection (`blocked_external`):** GDELT bulk collection was rate-limited (429) from
  the shared sandbox IP. Live/bulk news collection may stay blocked here; runs on a personal IP.
- **No real users (`simulated`):** recommendation, pricing, and experiment outcomes are
  simulations. No causal lift on real riders is claimed. Online learning / bandits stay
  prohibited.
- **Delayed labels (`pending_live_label`):** live-shadow forecasts stay `pending` until delayed
  ground-truth labels arrive (V2-08).
- **Assumptions (`assumption`):** margin, shortage externality, elasticity are assumption-set
  inputs, not measured economics. Profit/regret numbers are only as good as those assumptions.
- **Oracle is an upper bound:** Oracle net/regret is offline perfect-foresight, not achievable.
- **Research-only:** RL and QAOA are research-mode; simulator ≠ hardware; no quantum-advantage
  claim; they are not V2 completion conditions.
- **Elasticsearch optional:** search is an optional adapter; quantities/prices are hydrated from
  the operational ledger, never exposed raw from a search index.

## What would remove each limitation

| Limitation | Removed when |
|---|---|
| Event lift blocked | Enough overlapping real events collected + extraction + graph features non-zero in the holdout window, gate passes |
| External blocked | Collection run from an unthrottled IP populates fixtures |
| Simulated outcomes | Real user/operational logs exist (out of current scope) |
| Pending live labels | Delayed labels backfilled without leaking into past cutoffs |
| Assumption-based profit | Assumptions replaced with sourced/measured economics |
