"""Out-of-city rejection for borough assignment (CLAUDE.md §6.1, §22).

Regression tests for a measured defect: nearest-centroid assignment had no city boundary, so New
Jersey trips were silently absorbed into NYC boroughs. Feeding the Jersey City archives alongside
the NYC ones put JC/Hoboken demand into Manhattan and Staten Island, paired it with real NYC permit
events, and produced a spurious event lift (docs/EVENT_LIFT_FINDINGS.md).

The coordinates below are real station locations from the 2026-06 archives.
"""

from __future__ import annotations

from collections import Counter

from ml.forecasting.borough_event_lift import (
    REJECT_FAR_FROM_CENTROID,
    REJECT_IMPLAUSIBLE,
    REJECT_NEW_JERSEY,
    borough_of,
)

# Inside NYC — none of these may be rejected. Note the grain is a coarse nearest-centroid
# approximation (documented in the module), so a point's centroid is not always the borough a
# person would name: Astoria sits nearer the Manhattan centroid than the Queens one. These tests
# pin the *rejection* behaviour, which is what the boundary guard changes.
NYC_POINTS = [
    (40.71835, -73.98790),  # Lower East Side
    (40.75000, -73.99000),  # Midtown
    (40.67800, -73.97200),  # Prospect Heights
    (40.63500, -74.02600),  # Bay Ridge — west of the Hudson line but south of the cut
    (40.68510, -74.02100),  # the northernmost NYC point west of -74.02 in the data
    (40.75600, -73.92000),  # Astoria
    (40.82000, -73.92000),  # Mott Haven
    (40.70000, -73.80000),  # Jamaica, Queens
]

# Points whose nearest centroid is unambiguous — these pin the assignment itself.
NYC_ASSIGNMENTS = [
    (40.75000, -73.99000, "Manhattan"),
    (40.63500, -74.02600, "Brooklyn"),
    (40.70000, -73.80000, "Queens"),
    (40.85000, -73.88000, "Bronx"),
]

# (lat, lng) — New Jersey, must be rejected. Real JC/Hoboken station coordinates.
NEW_JERSEY_POINTS = [
    (40.71835, -74.03891),  # Columbus Drive, Jersey City (JC014)
    (40.71135, -74.06245),  # Pacific Ave & Communipaw Ave (JC118)
    (40.71821, -74.08364),  # Union St (JC051)
    (40.73370, -74.03810),  # Hoboken-ish, the JC median point
    (40.75450, -74.02400),  # the easternmost / northernmost JC point in the data
    (40.69220, -74.09470),  # the southernmost JC point in the data
]


def test_nyc_points_are_never_rejected() -> None:
    for lat, lng in NYC_POINTS:
        assert borough_of(lat, lng) is not None, f"{lat},{lng} is in NYC and must be kept"


def test_unambiguous_points_keep_their_borough() -> None:
    for lat, lng, expected in NYC_ASSIGNMENTS:
        assert borough_of(lat, lng) == expected, f"{lat},{lng} should stay {expected}"


def test_new_jersey_points_are_rejected() -> None:
    for lat, lng in NEW_JERSEY_POINTS:
        assert borough_of(lat, lng) is None, f"{lat},{lng} is New Jersey and must be rejected"


def test_jersey_city_no_longer_lands_in_staten_island() -> None:
    """The specific defect: JC is closer to the Staten Island centroid than to any other."""
    jc_lat, jc_lng = 40.71835, -74.03891
    assert borough_of(jc_lat, jc_lng) != "Staten Island"
    assert borough_of(jc_lat, jc_lng) is None


def test_rejection_reasons_are_counted_not_silent() -> None:
    reasons: Counter[str] = Counter()
    borough_of(40.71835, -74.03891, reasons)  # Jersey City
    borough_of(0.0, 0.0, reasons)  # nowhere
    borough_of(41.10, -73.45, reasons)  # inside the plausibility box, far from every centroid
    assert reasons[REJECT_NEW_JERSEY] == 1
    assert reasons[REJECT_IMPLAUSIBLE] == 1
    assert reasons[REJECT_FAR_FROM_CENTROID] == 1


def test_boundary_sits_in_the_measured_gap() -> None:
    """NYC data reaches lat 40.6851 west of the Hudson; JC starts at 40.6922 — reject between."""
    assert borough_of(40.6851, -74.0210) == "Brooklyn"
    assert borough_of(40.6922, -74.0240) is None


def test_accepted_points_do_not_increment_reasons() -> None:
    reasons: Counter[str] = Counter()
    assert borough_of(40.75000, -73.99000, reasons) == "Manhattan"
    assert sum(reasons.values()) == 0
