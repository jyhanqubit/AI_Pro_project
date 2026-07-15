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

# The Jersey City / Hoboken stations the demo golden-path event graph is wired to. These are real
# Citi Bike stations too; keeping them (default) means the event-aware forecast/rebalancing demo
# keeps working after a real import. Each carries its curated Korean name + aliases.
DEMO_ZONE_STATIONS: tuple[dict, ...] = (
    {
        "station_id": "JC_GROVE",
        "name": "Grove St PATH",
        "lat": 40.7196,
        "lng": -74.0431,
        "capacity": 20,
        "base_target": 6,
        "ko": "그로브 스트리트",
        "en": "Grove St PATH",
        "area": "저지시티",
        "aliases": ["grove", "그로브", "path"],
    },
    {
        "station_id": "JC_EXCHANGE",
        "name": "Exchange Place",
        "lat": 40.7166,
        "lng": -74.0329,
        "capacity": 18,
        "base_target": 5,
        "ko": "익스체인지 플레이스",
        "en": "Exchange Place",
        "area": "저지시티",
        "aliases": ["exchange", "익스체인지"],
    },
    {
        "station_id": "JC_HOBOKEN",
        "name": "Hoboken Terminal",
        "lat": 40.7360,
        "lng": -74.0301,
        "capacity": 20,
        "base_target": 6,
        "ko": "호보켄 터미널",
        "en": "Hoboken Terminal",
        "area": "호보켄",
        "aliases": ["hoboken", "호보켄", "터미널"],
    },
    {
        "station_id": "JC_CITYHALL",
        "name": "City Hall",
        "lat": 40.7377,
        "lng": -74.0324,
        "capacity": 18,
        "base_target": 6,
        "ko": "저지시티 시청",
        "en": "City Hall",
        "area": "저지시티",
        "aliases": ["city hall", "시청"],
    },
    {
        "station_id": "JC_NEWPORT",
        "name": "Newport",
        "lat": 40.7272,
        "lng": -74.0337,
        "capacity": 16,
        "base_target": 6,
        "ko": "뉴포트",
        "en": "Newport",
        "area": "저지시티",
        "aliases": ["newport", "뉴포트", "waterfront"],
    },
)
# Bikes for the demo zone stations (seed so the golden-path event drives shortage as designed).
_DEMO_ZONE_BIKES = {
    "JC_GROVE": 16,
    "JC_EXCHANGE": 13,
    "JC_HOBOKEN": 6,
    "JC_CITYHALL": 6,
    "JC_NEWPORT": 6,
}


def _parse_status_payload(payload: dict) -> dict[str, int]:
    return {
        str(s["station_id"]): int(s.get("num_bikes_available", 0))
        for s in payload.get("data", {}).get("stations", [])
    }


def _statuses(status_file: str | None = None) -> dict[str, int]:
    """Live bike counts by station_id: from a provided file, else the network (empty if neither)."""
    if status_file:
        return _parse_status_payload(json.loads(Path(status_file).read_text(encoding="utf-8")))

    from urllib.request import Request, urlopen

    from config.collectors import GBFS_STATION_STATUS_URL

    try:
        req = Request(GBFS_STATION_STATUS_URL, headers={"User-Agent": "ShockFlowAI/1.0"})
        with urlopen(req, timeout=10) as r:  # noqa: S310
            payload = json.loads(r.read())
        return _parse_status_payload(payload)
    except Exception:
        return {}


def _write_fixtures(
    stations: list[dict], *, status_file: str | None = None, keep_demo_zones: bool = True
) -> None:
    status = _statuses(status_file)
    reb_stations = []
    gaz_stations = []
    seen: set[str] = set()

    # Keep the demo event-zone stations first so the golden-path event demo still works.
    if keep_demo_zones:
        for s in DEMO_ZONE_STATIONS:
            seen.add(s["station_id"])
            bikes = status.get(
                s["station_id"], _DEMO_ZONE_BIKES.get(s["station_id"], s["base_target"])
            )
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
                    "ko": s["ko"],
                    "en": s["en"],
                    "area": s["area"],
                    "aliases": s["aliases"],
                }
            )

    for s in stations:
        if s["station_id"] in seen:
            continue  # real feed may include a demo-zone station under a different id; keep curated
        seen.add(s["station_id"])
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

    vehicle_capacity = max(18, round(len(reb_stations) * 1.5))
    REBALANCING_DEMO_FIXTURE.write_text(
        json.dumps(
            {
                "mode": "live",
                "description": (
                    "Real Citi Bike stations imported from GBFS station_information, plus the "
                    "Jersey City / Hoboken demo event-zone stations (kept so the event-aware "
                    "golden path still works). Bike counts from live station_status when provided."
                ),
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
                "description": (
                    "Real Citi Bike stations from GBFS station_information + curated demo "
                    "event-zone names (Jersey City / Hoboken)."
                ),
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
    ap.add_argument(
        "--status-file",
        default=None,
        help="a locally-downloaded GBFS station_status.json for current bike counts "
        "(optional; without it bikes seed at each station's base_target)",
    )
    ap.add_argument(
        "--no-demo-zones",
        action="store_true",
        help="do NOT keep the JC/Hoboken demo event-zone stations (the event demo then has no "
        "surge unless the imported region covers those zones)",
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

    _write_fixtures(stations, status_file=args.status_file, keep_demo_zones=not args.no_demo_zones)
    kept = 0 if args.no_demo_zones else len(DEMO_ZONE_STATIONS)
    print(
        f"Imported {len(stations)} real Citi Bike stations (+{kept} demo event-zone) -> fixtures."
    )
    print(f"  {REBALANCING_DEMO_FIXTURE.relative_to(_ROOT)}")
    print(f"  {STATION_GAZETTEER_FIXTURE.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
