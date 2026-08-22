"""V2-08 — run manifest + freshness monitoring over the committed V2 artifacts.

Scans every `reports/v2/**/*.json` result artifact and records a manifest row: which run produced it
(`run_id`), what may be claimed (`claim_status`), when it was produced (`freshness`), and how stale it
is now. This is the persistence/monitoring backbone: one index the cockpit, the V2-09 audit, and an
operator can read to see the state and age of every measured/simulated result at a glance.

Freshness/staleness is computed here; live-traffic *drift* (serving distribution vs training) needs a
live label stream we do not have, so it is reported as `blocked_data`, never faked. The delayed-label
loop that would feed drift/measured closure lives in `delayed_labels.py`.

Writes `reports/v2/monitoring/run_manifest.json`.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPORTS = Path("reports/v2")
OUT = REPORTS / "monitoring" / "run_manifest.json"
STALE_DAYS = 30.0


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def scan(now: datetime, reports: Path = REPORTS) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(reports.rglob("*.json")):
        if path.parent.name == "monitoring":
            continue  # don't index the monitor's own output
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(d, dict):
            continue
        fresh = _parse_dt(d.get("freshness"))
        age_h = round((now - fresh).total_seconds() / 3600, 1) if fresh else None
        rows.append({
            "artifact": str(path).replace("\\", "/"),
            "run_id": d.get("run_id"),
            "claim_status": d.get("claim_status"),
            "mode": d.get("mode"),
            "freshness": d.get("freshness"),
            "age_hours": age_h,
            "stale": (age_h is not None and age_h > STALE_DAYS * 24),
            "has_run_id": bool(d.get("run_id")),
        })
    return rows


def build(now: datetime) -> dict:
    rows = scan(now)
    by_status = Counter(r["claim_status"] for r in rows if r["claim_status"])
    ages = [r["age_hours"] for r in rows if r["age_hours"] is not None]
    return {
        "run_id": f"run_v2-08manifest_{now.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/monitoring/run_manifest.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": now.isoformat(),
        "generated_at": now.isoformat(),
        "n_artifacts": len(rows),
        "with_run_id": sum(r["has_run_id"] for r in rows),
        "by_claim_status": dict(sorted(by_status.items())),
        "stale_count": sum(r["stale"] for r in rows),
        "stale_threshold_days": STALE_DAYS,
        "oldest_age_hours": max(ages) if ages else None,
        "newest_age_hours": min(ages) if ages else None,
        "drift_note": "live-traffic drift (serving vs training distribution) requires a live label "
                      "stream — blocked_data here; freshness + delayed-label closure (delayed_labels.py) "
                      "are the available monitoring signals.",
        "artifacts": rows,
    }


def main(argv=None) -> int:
    now = datetime.now(UTC)
    report = build(now)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"V2-08 run manifest — {report['n_artifacts']} artifacts "
          f"({report['with_run_id']} with run_id), stale={report['stale_count']}")
    for s, n in report["by_claim_status"].items():
        print(f"  {s:18s} {n}")
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
