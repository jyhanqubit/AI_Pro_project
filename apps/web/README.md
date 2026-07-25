# ShockFlow AI — Operator UI (Phase 07)

Next.js (App Router, TypeScript strict) operator console for the offline replay demo. Four
screens follow the **Alert → Why → Simulate → Act** flow (CLAUDE.md §13):

- **Control Tower** — replay clock, event alerts, per-zone baseline vs event-aware forecast.
- **Why Changed** — Article → Event → H3 Zone → Feature trace with grounded evidence and the
  model-attributed delta.
- **Scenario Lab** — toggle events on/off and compare against the default forecast.
- **Rebalancing** — Phase 08 placeholder (the API returns 501; nothing is faked).

## Run (offline)

```bash
# 1) start the API (repo root)
make api                 # -> http://127.0.0.1:8000

# 2) start the UI (this folder)
cp .env.local.example .env.local     # NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
npm install
npm run dev              # -> http://localhost:3000
```

`npm run typecheck` and `npm run build` must pass (TypeScript strict). Historical Replay and Live
are visually distinct (the mode badge); loading, empty, and error states are handled.

## Notes

- Forecasts come from a labelled demo heuristic (`demo-heuristic-v1`), **not** the measured
  Phase 06 model; the event-aware delta is a transparent function of the graph event-exposure
  feature. Explanations are always evidence-backed.
- A self-contained, hosted snapshot of this console (real pipeline data baked in, no server
  needed) can be published as an Artifact for mobile viewing.
