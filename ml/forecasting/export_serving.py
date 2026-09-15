"""Export the serving feature snapshot for the promoted model (V2-07 wiring input).

Builds the dfv1 feature vectors for the **first hour after the training data ends** — the promoted
model's genuine next-hour out-of-sample serving point — and persists them as a small JSON artifact
the API can serve from without the raw trips.

Why this is leakage-safe by construction: every dfv1 feature at hour t is derived strictly from
hours < t (section 5.4; enforced by ``pipelines.features.lags``). Appending a placeholder cell at
``T+1`` therefore yields exactly the features a live system would have at that hour — the
placeholder's own (unknown) target never enters its features.

    python -m ml.forecasting.export_serving --data-dir data/raw/citibike
    make v2-serving-export

Output: ``reports/v2/holdout/serving_features.json`` — {serving_hour, feature_names, zones:[...]}.
The artifact is committed (small, intentional §15) so the deployed API can serve real model
predictions; regenerate it together with the model via ``make v2-holdout`` + this command.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import h3

from config.features import H3_RESOLUTION, LOCAL_TZ
from config.forecasting import REQUIRED_FEATURES
from contracts.demand import DemandCell
from contracts.enums import OperatingMode
from ml.forecasting.dataset import _collect_trips, resolve_trip_sources
from pipelines.features.aggregate import aggregate_demand
from pipelines.features.lags import build_demand_features

OUT_PATH = Path("reports/v2/holdout/serving_features.json")


def build_serving_rows(cells: list[DemandCell]) -> tuple[datetime, list]:
    """Feature rows for T+1 where T = last observed hour, one row per active zone."""
    last_hour = max(c.hour_start for c in cells)
    serving_hour = last_hour + timedelta(hours=1)
    # Serve only the currently-active network: zones with real demand in the final week. Stale
    # zones (a few trips months ago) would otherwise pass on zero-filled lag history alone.
    recent_floor = serving_hour - timedelta(days=7)
    last_seen: dict[str, datetime] = {}
    for c in cells:
        if c.zone_id not in last_seen or c.hour_start > last_seen[c.zone_id]:
            last_seen[c.zone_id] = c.hour_start
    zones = sorted(z for z, seen in last_seen.items() if seen >= recent_floor)
    placeholders = [
        DemandCell(
            zone_id=z,
            hour_start=serving_hour,
            departures=0,
            arrivals=0,
            net_flow=0,
            mode=OperatingMode.HISTORICAL_REPLAY,
        )
        for z in zones
    ]
    rows = build_demand_features(cells + placeholders)
    # Same usability rule as training (config.forecasting.REQUIRED_FEATURES): a zone must carry the
    # full lag history, so serving covers exactly the population the model was fit on.
    serving = [
        r
        for r in rows
        if r.hour_start == serving_hour
        and all(r.features.get(col) is not None for col in REQUIRED_FEATURES)
    ]
    return serving_hour, serving


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.export_serving")
    ap.add_argument("--data-dir", default="data/raw/citibike")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ns = ap.parse_args(argv)

    trips = _collect_trips(resolve_trip_sources(ns.data_dir))
    cells = aggregate_demand(trips, mode=OperatingMode.HISTORICAL_REPLAY, local_tz=LOCAL_TZ)
    serving_hour, rows = build_serving_rows(cells)
    if not rows:
        raise SystemExit("no serving rows built — is the data directory empty?")

    feature_names = sorted({k for r in rows for k in r.features})
    zones_out = []
    for r in rows:
        lat, lng = h3.cell_to_latlng(r.zone_id)
        zones_out.append(
            {
                "zone_id": r.zone_id,
                "lat": round(lat, 5),
                "lng": round(lng, 5),
                "features": {k: r.features.get(k) for k in feature_names},
            }
        )

    stamp = datetime.now(UTC)
    payload = {
        "run_id": f"run_v2-07serve_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/holdout/serving_features.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "generated_at": stamp.isoformat(),
        "serving_hour": serving_hour.isoformat(),
        "h3_resolution": H3_RESOLUTION,
        "feature_version": "dfv1",
        "n_zones": len(zones_out),
        "feature_names": feature_names,
        "zones": zones_out,
        "note": (
            "Feature vectors for the first hour after the training data ends (next-hour serving "
            "point). Leakage-safe by construction: dfv1 features at t use only hours < t."
        ),
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    size_kb = ns.out.stat().st_size / 1024
    print(f"serving features -> {ns.out}  ({len(zones_out)} zones, {size_kb:.0f} KB)")
    print(f"serving_hour: {serving_hour.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
