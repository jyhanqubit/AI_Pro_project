"""Demo anomaly scenario with injected synthetic faults (V1_Prompt §12).

Builds a short station-status history: a normal baseline plus four **synthetic** faults
(``is_synthetic_fault=True``) — a stale feed, an impossible capacity, a sudden depletion, and a
forecast residual — and one event that explains the depletion (so root cause can link it). Used by
the demo/API and to compute detector precision/recall on a labelled fixture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .detectors import StationObs
from .root_cause import EventLink

_TZ = timezone(timedelta(hours=-4))
_T0 = datetime(2026, 6, 30, 8, 0, tzinfo=_TZ)

# station_id -> (zone_id, capacity)
_STATIONS = {
    "JC_GROVE": ("892a1072e7bffff", 20),
    "JC_EXCHANGE": ("892a1072e3bffff", 18),
    "JC_HOBOKEN": ("892a107216bffff", 20),
    "JC_CITYHALL": ("892a10723b7ffff", 18),
    "JC_NEWPORT": ("892a1072ec7ffff", 16),
}
_N_STEPS = 6


def build_demo_scenario() -> tuple[list[StationObs], list[EventLink]]:
    obs: list[StationObs] = []
    for sid, (zone, cap) in _STATIONS.items():
        base = cap // 2
        for t in range(_N_STEPS):
            ts = _T0 + timedelta(hours=t)
            bikes = base + (t % 2)  # mild, stable fluctuation
            docks = cap - bikes
            obs.append(
                StationObs(
                    station_id=sid, zone_id=zone, ts=ts, bikes=bikes, docks=docks,
                    capacity=cap, last_reported=ts, forecast=float(bikes), actual=float(bikes),
                )
            )

    last = _T0 + timedelta(hours=_N_STEPS - 1)

    def _replace(sid: str, **kw) -> None:
        for i, o in enumerate(obs):
            if o.station_id == sid and o.ts == last:
                obs[i] = StationObs(**{**o.__dict__, **kw, "is_synthetic_fault": True})
                return

    # Fault 1 — stale feed (last_reported 60 min old) at Grove.
    _replace("JC_GROVE", last_reported=last - timedelta(minutes=60))
    # Fault 2 — impossible capacity at Exchange (bikes+docks > capacity).
    _replace("JC_EXCHANGE", bikes=15, docks=15)
    # Fault 3 — sudden depletion at City Hall (bikes -> 0). Explained by an event below.
    _replace("JC_CITYHALL", bikes=0, docks=18)
    # Fault 4 — forecast residual at Newport (actual far above forecast).
    _replace("JC_NEWPORT", forecast=5.0, actual=20.0)

    events = [
        EventLink(
            event_id="evt_transit_cityhall",
            zone_id="892a10723b7ffff",  # City Hall zone
            available_at=last - timedelta(minutes=30),
            article_ids=("a2",),
        )
    ]
    return obs, events
