"""Panel memory-window helpers (CLAUDE.md §11, §17).

A full multi-month NYC panel can exceed a laptop's RAM once expanded to per-zone-hour feature rows.
``--max-months`` bounds the panel to the most recent N calendar months of real demand — no
fabrication, just a shorter window. These pin the pure date-window logic (no I/O).
"""

from __future__ import annotations

from datetime import UTC, datetime

from contracts.demand import DemandCell
from contracts.enums import OperatingMode
from ml.forecasting.dataset import _months_before, _window_cells


def _cell(year: int, month: int) -> DemandCell:
    return DemandCell(
        zone_id="z",
        hour_start=datetime(year, month, 1, 12, tzinfo=UTC),
        departures=1,
        arrivals=1,
        net_flow=0,
        departures_member=1,
        departures_casual=0,
        mode=OperatingMode.HISTORICAL_REPLAY,
    )


def test_months_before_crosses_year_boundary() -> None:
    assert _months_before(datetime(2026, 6, 1, tzinfo=UTC), 5) == datetime(2026, 1, 1, tzinfo=UTC)
    assert _months_before(datetime(2026, 2, 1, tzinfo=UTC), 3) == datetime(2025, 11, 1, tzinfo=UTC)


def test_window_keeps_recent_months_only() -> None:
    cells = [_cell(2026, m) for m in range(1, 7)]  # Jan..Jun 2026
    kept = _window_cells(cells, max_months=3)  # keep Apr, May, Jun
    months = sorted({c.hour_start.month for c in kept})
    assert months == [4, 5, 6]


def test_window_none_keeps_everything() -> None:
    cells = [_cell(2026, m) for m in range(1, 7)]
    assert _window_cells(cells, None) is cells


def test_window_on_empty_is_safe() -> None:
    assert _window_cells([], max_months=3) == []
