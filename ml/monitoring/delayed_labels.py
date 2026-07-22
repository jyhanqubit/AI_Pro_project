"""V2-08 — delayed-label loop: close `pending_live_label` → `measured` WITHOUT leaking into cutoffs.

A live-shadow forecast made at ``forecast_cutoff`` for a future ``target_hour`` cannot be scored until
the true demand for that hour actually arrives — which is *after* the target hour. Until then the
forecast is ``pending_live_label``. When the label arrives it flips to ``measured``.

The one rule that must never break (base-contract §5.2 availability):

    a label may CLOSE a forecast only if the label became available AFTER the forecast was made,
    i.e. ``label.available_at > forecast.forecast_cutoff``.

Otherwise you would be "scoring" a forecast with information that predates it — a leak. Such a label
is rejected as ``leakage_rejected``; it never silently closes a forecast. This is the whole point of
the phase acceptance ("delayed-label backfill does not leak into past cutoffs").

Pure and unit-tested; the runner demonstrates the loop on a fixture (``demo_fixture``) because there
is no live shadow-forecast stream here — the mechanism is the deliverable, not a live number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

OUT = Path("reports/v2/monitoring/delayed_labels.json")


@dataclass(frozen=True)
class PendingForecast:
    zone_id: str
    forecast_cutoff: datetime   # when the forecast was made (information boundary)
    target_hour: datetime       # the hour being predicted (>= cutoff)
    predicted: float


@dataclass(frozen=True)
class ArrivedLabel:
    zone_id: str
    target_hour: datetime       # the hour this actual demand is for
    actual: float
    available_at: datetime      # when this label became known to the system


def resolve(pending: list[PendingForecast], labels: list[ArrivedLabel]) -> dict:
    """Match labels to pending forecasts under the availability rule; score only leak-safe closures."""
    # index labels by (zone, target_hour); keep the EARLIEST-available label per key
    by_key: dict[tuple[str, str], ArrivedLabel] = {}
    for lb in labels:
        k = (lb.zone_id, lb.target_hour.isoformat())
        cur = by_key.get(k)
        if cur is None or lb.available_at < cur.available_at:
            by_key[k] = lb

    closed, still_pending, leaked = [], [], []
    for f in pending:
        lb = by_key.get((f.zone_id, f.target_hour.isoformat()))
        if lb is None:
            still_pending.append({"zone_id": f.zone_id, "target_hour": f.target_hour.isoformat(),
                                  "reason": "no_label_yet"})
            continue
        if lb.available_at <= f.forecast_cutoff:
            # label predates (or equals) the forecast -> using it would leak. Reject; stay pending.
            leaked.append({"zone_id": f.zone_id, "target_hour": f.target_hour.isoformat(),
                           "forecast_cutoff": f.forecast_cutoff.isoformat(),
                           "label_available_at": lb.available_at.isoformat()})
            still_pending.append({"zone_id": f.zone_id, "target_hour": f.target_hour.isoformat(),
                                  "reason": "leakage_rejected"})
            continue
        closed.append({"zone_id": f.zone_id, "target_hour": f.target_hour.isoformat(),
                       "predicted": f.predicted, "actual": lb.actual,
                       "abs_error": abs(f.predicted - lb.actual),
                       "claim_status": "measured"})

    denom = sum(abs(c["actual"]) for c in closed)
    wape = round(sum(c["abs_error"] for c in closed) / denom, 4) if denom else None
    return {
        "n_pending_in": len(pending),
        "n_closed_measured": len(closed),
        "n_still_pending": len(still_pending),
        "n_leakage_rejected": len(leaked),
        "closed_wape": wape,
        "closed": closed,
        "still_pending": still_pending,
        "leakage_rejected": leaked,
    }


def _demo(now: datetime) -> tuple[list[PendingForecast], list[ArrivedLabel]]:
    """A tiny fixture: two forecasts get valid delayed labels; one label is leaky (predates cutoff)."""
    def h(s: str) -> datetime:
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    pending = [
        PendingForecast("JC-A", h("2026-05-01T14:00"), h("2026-05-01T18:00"), 30.0),
        PendingForecast("JC-B", h("2026-05-01T14:00"), h("2026-05-01T18:00"), 20.0),
        PendingForecast("JC-C", h("2026-05-01T14:00"), h("2026-05-01T18:00"), 10.0),  # no label -> pending
    ]
    labels = [
        # valid: available AFTER the 14:00 cutoff (label for the 18:00 hour arrives ~19:05)
        ArrivedLabel("JC-A", h("2026-05-01T18:00"), 33.0, h("2026-05-01T19:05")),
        # LEAKY: claims to be "available" at 13:00 — before the 14:00 forecast -> must be rejected
        ArrivedLabel("JC-B", h("2026-05-01T18:00"), 25.0, h("2026-05-01T13:00")),
    ]
    return pending, labels


def main(argv=None) -> int:
    now = datetime.now(UTC)
    pending, labels = _demo(now)
    res = resolve(pending, labels)
    report = {
        "run_id": f"run_v2-08labels_{now.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/monitoring/delayed_labels.json",
        "mode": "demo_fixture", "claim_status": "demo_fixture", "freshness": now.isoformat(),
        "rule": "a label closes a forecast only if label.available_at > forecast.forecast_cutoff "
                "(base-contract §5.2); otherwise leakage_rejected and the forecast stays pending",
        "note": "Demonstrates the leakage-safe pending_live_label -> measured loop on a fixture; a "
                "real close requires the live shadow-forecast stream (blocked here). The mechanism, "
                "not the numbers, is the deliverable.",
        **res,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"V2-08 delayed labels — closed(measured)={res['n_closed_measured']} "
          f"still_pending={res['n_still_pending']} leakage_rejected={res['n_leakage_rejected']}")
    print(f"  closed WAPE={res['closed_wape']}")
    print(f"  leakage guard rejected {res['n_leakage_rejected']} label(s) that predated their cutoff")
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
