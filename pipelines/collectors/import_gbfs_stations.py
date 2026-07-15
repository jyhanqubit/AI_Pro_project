"""Write the app's station fixtures from the live Citi Bike GBFS network (V2).

Fetches the real ``station_information`` feed (free, no key), optionally filters to a bounding box
and/or caps the count, then writes ``data/fixtures/rebalancing_demo.json`` (coords / capacity /
base_target) and ``data/fixtures/station_gazetteer.json`` (names). After this, search / map /
statistics / pricing / allocation all run on the real network.

Requires outbound network. On failure it prints the reason and leaves the existing fixtures
untouched (Demo Mode keeps working). Merges live ``station_status`` for current bike counts when
available; otherwise seeds bikes at base_target.

    python -m pipelines.collectors.import_gbfs_stations --limit 40 --bbox 40.70,40.78,-74.05,-73.95
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config.collectors import (
    REBALANCING_DEMO_FIXTURE,
    STATION_GAZETTEER_FIXTURE,
)
from pipelines.collectors.gbfs_stations import (
    BBox,
    StationImportUnavailable,
    fetch_station_information,
    parse_station_information,
)

_ROOT = Path(__file__).resolve().parents[2]


def _statuses() -> dict[str, int]:
    """Best-effort live bike counts by station_id (empty if unavailable)."""
    from urllib.request import Request, urlopen

    from config.collectors import GBFS_STATION_STATUS_URL

    try:
        req = Request(GBFS_STATION_STATUS_URL, headers={"User-Agent": "ShockFlowAI/1.0"})
        with urlopen(req, timeout=10) as r:  # noqa: S310
            payload = json.loads(r.read())
        return {
            str(s["station_id"]): int(s.get("num_bikes_available", 0))
            for s in payload.get("data", {}).get("stations", [])
        }
    except Exception:
        return {}


def _write_fixtures(stations: list[dict]) -> None:
    status = _statuses()
    reb_stations = []
    gaz_stations = []
    for s in stations:
        bikes = status.get(s["station_id"], s["base_target"])  # seed at target if no live status
        reb_stations.append(
            {
                "station_id": s["station_id"],
                "name": s["name"],
                "lat": s["lat"],
                "lng": s["lng"],
                "bikes_available": min(bikes, s["capacity"]),
                "capacity": s["capacity"],
                "base_target": s["base_target"],
            }
        )
        gaz_stations.append(
            {
                "station_id": s["station_id"],
                "ko": s["name"],
                "en": s["name"],
                "area": "NYC",
                "aliases": [],
            }
        )

    vehicle_capacity = max(18, round(len(stations) * 1.5))
    REBALANCING_DEMO_FIXTURE.write_text(
        json.dumps(
            {
                "mode": "live",
                "description": "Imported from Citi Bike GBFS station_information (real network).",
                "vehicle_capacity": vehicle_capacity,
                "stations": reb_stations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    STATION_GAZETTEER_FIXTURE.write_text(
        json.dumps(
            {
                "description": "Imported from Citi Bike GBFS station_information (real network).",
                "stations": gaz_stations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40, help="max stations to import (0 = all)")
    ap.add_argument("--bbox", default=None, help="lat_min,lat_max,lng_min,lng_max")
    ap.add_argument(
        "--from-file",
        default=None,
        help="parse a locally-downloaded GBFS station_information.json instead of the network "
        "(use when this host has no egress: download the feed in a browser, then import the file)",
    )
    args = ap.parse_args()

    bbox = None
    if args.bbox:
        a, b, c, d = (float(x) for x in args.bbox.split(","))
        bbox = BBox(a, b, c, d)

    if args.from_file:
        raw = Path(args.from_file).read_bytes()
        stations = parse_station_information(raw, bbox=bbox, limit=args.limit)
    else:
        try:
            stations = fetch_station_information(bbox=bbox, limit=args.limit)
        except StationImportUnavailable as e:
            print(f"station import degraded: {e}")
            print("Existing fixtures left untouched. Re-run where outbound network is available,")
            print("or download station_information.json and pass it with --from-file PATH.")
            return 1

    if not stations:
        print("No stations matched the filter; fixtures left untouched.")
        return 1

    _write_fixtures(stations)
    print(f"Imported {len(stations)} real Citi Bike stations -> fixtures.")
    print(f"  {REBALANCING_DEMO_FIXTURE.relative_to(_ROOT)}")
    print(f"  {STATION_GAZETTEER_FIXTURE.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
