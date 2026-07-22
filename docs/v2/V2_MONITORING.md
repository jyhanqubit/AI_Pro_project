# V2-08 — Persistence, Monitoring & Delayed Labels

Two artifact-backed mechanisms (`make v2-monitor`), each pure + unit-tested
(`tests/unit/test_v2_monitoring.py`).

## 1. Run manifest + freshness monitoring (`ml/monitoring/run_manifest.py`)

Scans every `reports/v2/**/*.json` result and writes `reports/v2/monitoring/run_manifest.json`: one
row per artifact with `run_id`, `claim_status`, `mode`, `freshness`, `age_hours`, and a `stale` flag
(> 30 days). It is the single index the cockpit / V2-09 audit / an operator can read to see the state
and age of every result.

Current scan: **26 artifacts, all with a `run_id`, 0 stale** — by claim_status: measured 15,
offline_benchmark 5, simulated 5, blocked_data 1.

**Drift, honestly:** live-traffic drift (serving distribution vs training) needs a live label stream
we do not have here, so it is reported as `blocked_data`, never faked. Freshness/staleness and the
delayed-label closure below are the monitoring signals that *are* available.

## 2. Delayed-label loop (`ml/monitoring/delayed_labels.py`) — the leakage guard

A live-shadow forecast made at `forecast_cutoff` for a future `target_hour` stays `pending_live_label`
until the true demand arrives; then it flips to `measured`. The rule that must never break
(base-contract §5.2):

> a label may close a forecast **only if `label.available_at > forecast.forecast_cutoff`** —
> otherwise scoring it would use information that predates the forecast (a leak).

A label whose availability is at or before the cutoff is **`leakage_rejected`** and the forecast
stays pending — it never silently closes. This is the phase's key acceptance ("delayed-label backfill
does not leak into past cutoffs"), verified by unit tests including the exactly-at-cutoff boundary.

The runner demonstrates the loop on a `demo_fixture` (there is no live shadow-forecast stream here):
2 pending forecasts + a valid delayed label + one deliberately leaky label → **1 closed (measured),
1 leakage-rejected, 1 still pending**. The mechanism — not the demo numbers — is the deliverable; a
real close requires the live stream (`blocked` here).

## Acceptance status

- Artifacts persisted with run manifests — **done** (`run_manifest.json`).
- Monitoring surfaces freshness — **done**; drift — `blocked_data` (no live labels), stated honestly.
- Delayed-label backfill does not leak into past cutoffs — **done + tested** (strict `>` guard).
