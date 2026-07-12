"""Demand aggregation and lag-leakage tests. CLAUDE.md sections 4, 5.4, 17."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from contracts.demand import DemandCell
from contracts.enums import OperatingMode, RiderType
from contracts.trip import TripRecord
from pipelines.features import aggregate_demand, build_demand_features, zone_for

NY = ZoneInfo("America/New_York")
H0 = datetime(2026, 6, 15, 8, tzinfo=NY)

# Two distinct Jersey City coordinates that fall in different H3 res-9 cells.
GROVE = (40.7196, -74.0431)
HOBOKEN = (40.7360, -74.0301)


def _trip(start, end, t_start, dur_min=10, rider_type=None):
    return TripRecord(
        trip_id=f"{t_start.isoformat()}-{start}-{end}",
        started_at=t_start,
        ended_at=t_start + timedelta(minutes=dur_min),
        start_station_id="s",
        end_station_id="e",
        start_lat=start[0],
        start_lng=start[1],
        end_lat=end[0],
        end_lng=end[1],
        source_file="test",
        loaded_at=t_start,
        rider_type=rider_type,
    )


# --- Aggregation ----------------------------------------------------------


def test_aggregate_counts_and_net_flow():
    trips = [
        _trip(GROVE, HOBOKEN, H0),  # Grove departure, Hoboken arrival
        _trip(GROVE, HOBOKEN, H0 + timedelta(minutes=5)),  # another Grove departure
        _trip(HOBOKEN, GROVE, H0),  # Hoboken departure, Grove arrival
    ]
    cells = aggregate_demand(trips, mode=OperatingMode.DEMO_FIXTURE)
    by_zone = {c.zone_id: c for c in cells}

    grove = zone_for(*GROVE)
    hob = zone_for(*HOBOKEN)

    assert by_zone[grove].departures == 2
    assert by_zone[grove].arrivals == 1
    assert by_zone[grove].net_flow == -1  # arrivals - departures
    assert by_zone[hob].departures == 1
    assert by_zone[hob].arrivals == 2
    assert by_zone[hob].net_flow == 1


def test_aggregate_buckets_by_local_hour():
    trips = [
        _trip(GROVE, HOBOKEN, H0),
        _trip(GROVE, HOBOKEN, H0 + timedelta(hours=1)),  # next hour
    ]
    cells = aggregate_demand(trips)
    grove_cells = sorted(
        (c for c in cells if c.zone_id == zone_for(*GROVE)), key=lambda c: c.hour_start
    )
    assert len(grove_cells) == 2
    assert grove_cells[0].departures == 1
    assert grove_cells[1].departures == 1


# --- Leakage-safe lag / rolling features (section 5.4) --------------------


def _panel(departures_by_hour: list[int], zone: str = "z") -> list[DemandCell]:
    cells = []
    for i, dep in enumerate(departures_by_hour):
        cells.append(
            DemandCell(
                zone_id=zone,
                hour_start=H0 + timedelta(hours=i),
                departures=dep,
                arrivals=0,
                net_flow=-dep,
                mode=OperatingMode.DEMO_FIXTURE,
            )
        )
    return cells


def test_lag_1_equals_previous_hour_and_excludes_current():
    cells = _panel([10, 20, 30, 40])
    rows = {
        r.hour_start: r for r in build_demand_features(cells, lag_hours=(1,), rolling_windows=())
    }

    r0 = rows[H0]
    r1 = rows[H0 + timedelta(hours=1)]
    r3 = rows[H0 + timedelta(hours=3)]

    assert r0.features["dep_lag_1"] is None  # no prior hour
    assert r1.features["dep_lag_1"] == 10.0  # previous hour's value
    assert r3.features["dep_lag_1"] == 30.0
    # The current target value (40 at r3) must not equal its own lag.
    assert r3.targets["departures"] == 40
    assert r3.features["dep_lag_1"] != 40.0


def test_rolling_mean_is_shifted_and_excludes_current():
    cells = _panel([10, 20, 30, 40])
    rows = {
        r.hour_start: r for r in build_demand_features(cells, lag_hours=(), rolling_windows=(3,))
    }

    r3 = rows[H0 + timedelta(hours=3)]
    # Trailing 3 hours strictly before t=3 -> mean(10, 20, 30) = 20, not including 40.
    assert r3.features["dep_roll_mean_3"] == 20.0
    r2 = rows[H0 + timedelta(hours=2)]
    assert r2.features["dep_roll_mean_3"] is None  # fewer than 3 prior hours


def test_changing_current_value_does_not_change_past_features():
    base = build_demand_features(_panel([10, 20, 30, 40]), lag_hours=(1,), rolling_windows=(3,))
    bumped = build_demand_features(_panel([10, 20, 30, 999]), lag_hours=(1,), rolling_windows=(3,))
    by_hour_base = {r.hour_start: r for r in base}
    by_hour_bumped = {r.hour_start: r for r in bumped}

    # Features at hour 2 (before the changed hour 3) must be identical.
    h2 = H0 + timedelta(hours=2)
    assert by_hour_base[h2].features == by_hour_bumped[h2].features


def test_momentum_is_short_over_long_mean():
    cells = _panel([10, 20, 30, 40])
    rows = {
        r.hour_start: r
        for r in build_demand_features(
            cells, lag_hours=(), rolling_windows=(), momentum_windows=(1, 3)
        )
    }
    r3 = rows[H0 + timedelta(hours=3)]
    # short=mean(s[2:3])=30, long=mean(s[0:3])=20 -> 1.5 (surge above baseline).
    assert r3.features["dep_momentum"] == pytest.approx(1.5, rel=1e-4)
    r1 = rows[H0 + timedelta(hours=1)]
    assert r1.features["dep_momentum"] is None  # not enough history for long window


def test_expanding_mean_uses_only_prior_hours():
    cells = _panel([10, 20, 30, 40])
    rows = {r.hour_start: r for r in build_demand_features(cells, lag_hours=(), rolling_windows=())}
    r3 = rows[H0 + timedelta(hours=3)]
    assert r3.features["dep_expanding_mean"] == pytest.approx(20.0)  # mean(10,20,30)
    assert rows[H0].features["dep_expanding_mean"] is None  # no prior hours


def test_net_cumsum_day_accumulates_prior_hours_only():
    cells = _panel([10, 20, 30, 40])  # net_flow = -dep
    rows = {r.hour_start: r for r in build_demand_features(cells, lag_hours=(), rolling_windows=())}
    r3 = rows[H0 + timedelta(hours=3)]
    # Prior same-day net flows: -10 + -20 + -30 = -60 (excludes current hour).
    assert r3.features["net_cumsum_day"] == pytest.approx(-60.0)
    assert rows[H0].features["net_cumsum_day"] == pytest.approx(0.0)  # first hour, no pressure yet


def test_aggregate_splits_member_and_casual():
    trips = [
        _trip(GROVE, HOBOKEN, H0, rider_type=RiderType.MEMBER),
        _trip(GROVE, HOBOKEN, H0 + timedelta(minutes=5), rider_type=RiderType.MEMBER),
        _trip(GROVE, HOBOKEN, H0 + timedelta(minutes=8), rider_type=RiderType.CASUAL),
    ]
    cell = next(c for c in aggregate_demand(trips) if c.zone_id == zone_for(*GROVE))
    assert cell.departures == 3
    assert cell.departures_member == 2
    assert cell.departures_casual == 1


def test_member_share_lag_is_leakage_safe():
    # Same zone/hour a week apart: 3 member + 1 casual -> share 0.75 at the earlier hour.
    z = "z"
    early = DemandCell(
        zone_id=z,
        hour_start=H0,
        departures=4,
        arrivals=0,
        net_flow=-4,
        departures_member=3,
        departures_casual=1,
        mode=OperatingMode.DEMO_FIXTURE,
    )
    later = DemandCell(
        zone_id=z,
        hour_start=H0 + timedelta(hours=168),
        departures=1,
        arrivals=0,
        net_flow=-1,
        departures_member=1,
        departures_casual=0,
        mode=OperatingMode.DEMO_FIXTURE,
    )
    rows = {
        r.hour_start: r for r in build_demand_features([early, later], member_share_lags=(168,))
    }
    r_later = rows[H0 + timedelta(hours=168)]
    assert r_later.features["member_share_lag_168"] == pytest.approx(0.75)
    # No prior week for the earlier hour -> feature absent.
    assert rows[H0].features["member_share_lag_168"] is None


def test_missing_hours_treated_as_zero_in_lags():
    # Observed at hours 0 and 2 only; hour 1 is a gap (0 demand).
    cells = [
        DemandCell(
            zone_id="z",
            hour_start=H0,
            departures=5,
            arrivals=0,
            net_flow=-5,
            mode=OperatingMode.DEMO_FIXTURE,
        ),
        DemandCell(
            zone_id="z",
            hour_start=H0 + timedelta(hours=2),
            departures=7,
            arrivals=0,
            net_flow=-7,
            mode=OperatingMode.DEMO_FIXTURE,
        ),
    ]
    rows = {
        r.hour_start: r for r in build_demand_features(cells, lag_hours=(1,), rolling_windows=())
    }
    # At hour 2, lag_1 refers to the gap hour 1, which is 0 demand.
    assert rows[H0 + timedelta(hours=2)].features["dep_lag_1"] == 0.0
