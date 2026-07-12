"""Demand aggregation. CLAUDE.md sections 4 and 5.3.

Aggregates trips into the primary grain (H3 zone x local hour), counting departures at the
start zone/hour and arrivals at the end zone/hour. Timestamps are converted to local time
before bucketing. This is a demand label, never an inventory-difference estimate (section 22).
"""

from __future__ import annotations

from collections import Counter
from zoneinfo import ZoneInfo

from config.features import H3_RESOLUTION, LOCAL_TZ
from contracts.demand import DemandCell
from contracts.enums import OperatingMode, RiderType
from contracts.trip import TripRecord

from .temporal import to_local_hour
from .zones import zone_for


def aggregate_demand(
    trips: list[TripRecord],
    *,
    mode: OperatingMode = OperatingMode.DEMO_FIXTURE,
    resolution: int = H3_RESOLUTION,
    local_tz: str = LOCAL_TZ,
) -> list[DemandCell]:
    """Aggregate trips into demand cells sorted by (hour_start, zone_id)."""
    tz = ZoneInfo(local_tz)
    departures: Counter[tuple[str, str]] = Counter()
    arrivals: Counter[tuple[str, str]] = Counter()
    dep_member: Counter[tuple[str, str]] = Counter()
    dep_casual: Counter[tuple[str, str]] = Counter()
    # Keep the aware hour_start keyed by its ISO string for stable, hashable grouping.
    hour_by_key: dict[str, object] = {}

    for trip in trips:
        dep_zone = zone_for(trip.start_lat, trip.start_lng, resolution)
        dep_hour = to_local_hour(trip.started_at, tz)
        dep_key = dep_hour.isoformat()
        departures[(dep_zone, dep_key)] += 1
        hour_by_key[dep_key] = dep_hour
        if trip.rider_type is RiderType.MEMBER:
            dep_member[(dep_zone, dep_key)] += 1
        elif trip.rider_type is RiderType.CASUAL:
            dep_casual[(dep_zone, dep_key)] += 1

        arr_zone = zone_for(trip.end_lat, trip.end_lng, resolution)
        arr_hour = to_local_hour(trip.ended_at, tz)
        arr_key = arr_hour.isoformat()
        arrivals[(arr_zone, arr_key)] += 1
        hour_by_key[arr_key] = arr_hour

    cells: list[DemandCell] = []
    for zone, hour_key in departures.keys() | arrivals.keys():
        dep = departures.get((zone, hour_key), 0)
        arr = arrivals.get((zone, hour_key), 0)
        cells.append(
            DemandCell(
                zone_id=zone,
                hour_start=hour_by_key[hour_key],  # type: ignore[arg-type]
                departures=dep,
                arrivals=arr,
                net_flow=arr - dep,
                departures_member=dep_member.get((zone, hour_key), 0),
                departures_casual=dep_casual.get((zone, hour_key), 0),
                mode=mode,
            )
        )

    cells.sort(key=lambda c: (c.hour_start, c.zone_id))
    return cells
