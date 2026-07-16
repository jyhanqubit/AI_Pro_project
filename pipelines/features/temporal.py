"""Temporal kernels for demand aggregation. CLAUDE.md section 5.3.

Pure functions handling timezone localization with explicit DST semantics. Ambiguous
(fall-back) and nonexistent (spring-forward) local times are never silently dropped:
they are resolved deterministically and flagged.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")

DstStatus = Literal["normal", "ambiguous", "nonexistent"]


def classify_local(naive: datetime, tz: ZoneInfo) -> DstStatus:
    """Classify a naive wall-clock time against DST transitions in ``tz``."""
    if naive.tzinfo is not None:
        raise ValueError("classify_local expects a naive datetime")

    # Nonexistent: an imaginary wall time does not round-trip through UTC.
    aware = naive.replace(tzinfo=tz)
    if aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != naive:
        return "nonexistent"

    # Ambiguous: the two folds resolve to different UTC offsets (fall-back overlap).
    if naive.replace(tzinfo=tz, fold=0).utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset():
        return "ambiguous"

    return "normal"


def localize(naive: datetime, tz: ZoneInfo) -> tuple[datetime, DstStatus]:
    """Localize a naive wall-clock time, resolving DST explicitly.

    Returns (aware_datetime, status). Nothing is dropped:
    - ambiguous  -> earlier occurrence (fold=0, e.g. EDT during fall-back).
    - nonexistent -> shifted forward by the one-hour gap to the next valid instant.
    """
    status = classify_local(naive, tz)
    if status == "nonexistent":
        return (naive + timedelta(hours=1)).replace(tzinfo=tz), status
    if status == "ambiguous":
        return naive.replace(tzinfo=tz, fold=0), status
    return naive.replace(tzinfo=tz), status


def to_local_hour(aware: datetime, tz: ZoneInfo) -> datetime:
    """Floor an aware timestamp to the start of its local hour (timezone-aware)."""
    if aware.tzinfo is None:
        raise ValueError("to_local_hour expects a timezone-aware datetime")
    local = aware.astimezone(tz)
    return local.replace(minute=0, second=0, microsecond=0)


# Guard against a pathological span: a single corrupt/mis-parsed timestamp (e.g. a birth-year or
# epoch value read as a date) would otherwise make the gap-free grid billions of hours long and
# exhaust memory. Any legitimate single panel is far under this (10 years of hours).
MAX_DENSE_SPAN_HOURS = 10 * 366 * 24


class DenseSpanTooLarge(ValueError):
    """The observed hour span is implausibly large — almost always a corrupt timestamp."""


def dense_hourly_index(local_hours: list[datetime], tz: ZoneInfo) -> list[datetime]:
    """Build a gap-free hourly index (local, aware) spanning the observed hours.

    Steps in UTC so DST-transition days yield the correct 23- or 25-hour spans and each
    distinct instant maps to exactly one bucket. Raises :class:`DenseSpanTooLarge` if the span is
    implausibly wide (a corrupt timestamp) rather than exhausting memory.
    """
    if not local_hours:
        return []
    instants = sorted({h.astimezone(UTC) for h in local_hours})
    start, end = instants[0], instants[-1]
    span_hours = (end - start).total_seconds() / 3600.0
    if span_hours > MAX_DENSE_SPAN_HOURS:
        raise DenseSpanTooLarge(
            f"observed hour span {start.isoformat()} .. {end.isoformat()} is "
            f"{span_hours / 24 / 365:.1f} years — likely a corrupt timestamp in the trip data. "
            "Drop the bad rows, or bound the panel with --max-months."
        )
    index: list[datetime] = []
    cur = start
    while cur <= end:
        index.append(cur.astimezone(tz))
        cur += timedelta(hours=1)
    return index
