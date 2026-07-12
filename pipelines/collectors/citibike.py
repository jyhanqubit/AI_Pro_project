"""Citi Bike trip-history collector. CLAUDE.md sections 7.1, 6.1, 5.3.

Reads local CSV or ZIP files under ``data/raw/citibike/``. Column aliases come from
configuration. Naive source timestamps are localized to the configured local timezone
(America/New_York), producing timezone-aware ``TripRecord`` timestamps. Invalid rows are
excluded and counted by reason, never silently dropped.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from config.collectors import CITIBIKE_COLUMN_ALIASES
from contracts.enums import OperatingMode, RiderType
from contracts.trip import TripRecord
from pipelines.features.temporal import localize

from .base import (
    CollectionMetadata,
    CollectionResult,
    Collector,
    schema_hash_from_headers,
)

_RIDER_ALIASES = {
    "member": RiderType.MEMBER,
    "subscriber": RiderType.MEMBER,
    "casual": RiderType.CASUAL,
    "customer": RiderType.CASUAL,
}


def _resolve_aliases(headers: list[str]) -> dict[str, str]:
    """Map canonical field -> actual header present in this file (case-insensitive)."""
    lookup = {h.strip().lower(): h for h in headers}
    resolved: dict[str, str] = {}
    for field, aliases in CITIBIKE_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias.strip().lower() in lookup:
                resolved[field] = lookup[alias.strip().lower()]
                break
    return resolved


def _parse_local(raw: str, tz: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(raw.strip())
    if dt.tzinfo is None:
        # Citi Bike wall-clock times are local New York time; localize with explicit
        # DST handling so ambiguous/nonexistent times are resolved, never dropped (5.3).
        dt, _status = localize(dt, tz)
    return dt


def _classify_error(exc: Exception) -> str:
    """Bucket a row failure into a stable, human-readable exclusion reason."""
    if isinstance(exc, ValidationError):
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            etype = err.get("type", "")
            if "lat" in loc or "lng" in loc:
                if etype in {"greater_than_equal", "less_than_equal"}:
                    return "coordinate_out_of_range"
                return "invalid_coordinate"
            if etype == "missing":
                return f"missing_field:{loc}"
            if "ended_at must not be before" in str(err.get("msg", "")):
                return "end_before_start"
        return "schema_validation_error"
    if isinstance(exc, ValueError):
        msg = str(exc)
        if msg.startswith("missing_coordinate"):
            return "missing_coordinate"
        return "unparseable_row"
    if isinstance(exc, KeyError):
        return "unparseable_row"
    return "unknown_error"


class CitiBikeCollector(Collector[TripRecord]):
    name = "citibike"

    def __init__(
        self,
        path: str | Path,
        *,
        mode: OperatingMode = OperatingMode.DEMO_FIXTURE,
        local_tz: str = "America/New_York",
    ) -> None:
        self.path = Path(path)
        self.mode = mode
        self.tz = ZoneInfo(local_tz)

    def _iter_rows(self) -> Iterator[tuple[list[str], dict[str, str]]]:
        """Yield (headers, row) for each data row, from a CSV or a ZIP of CSVs."""
        if self.path.suffix.lower() == ".zip":
            with zipfile.ZipFile(self.path) as zf:
                for name in zf.namelist():
                    base = name.rsplit("/", 1)[-1]
                    # Skip non-CSV entries and macOS archive junk (__MACOSX, ._ forks).
                    if not name.lower().endswith(".csv"):
                        continue
                    if name.startswith("__MACOSX/") or base.startswith("._"):
                        continue
                    with zf.open(name) as fh:
                        text = io.TextIOWrapper(fh, encoding="utf-8-sig")
                        reader = csv.DictReader(text)
                        headers = reader.fieldnames or []
                        for row in reader:
                            yield list(headers), row
        else:
            with self.path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                headers = reader.fieldnames or []
                for row in reader:
                    yield list(headers), row

    def _build_record(
        self, resolved: dict[str, str], row: dict[str, str], row_index: int
    ) -> TripRecord:
        def val(field: str) -> str:
            header = resolved.get(field)
            return (row.get(header, "") if header else "").strip()

        def coord(field: str) -> float:
            raw = val(field)
            if raw == "":
                # Trips with an unrecorded end (missing coords) are a known Citi Bike quirk.
                raise ValueError(f"missing_coordinate:{field}")
            return float(raw)

        trip_id = val("trip_id") or f"{self.path.name}:{row_index}"
        return TripRecord(
            trip_id=trip_id,
            started_at=_parse_local(val("started_at"), self.tz),
            ended_at=_parse_local(val("ended_at"), self.tz),
            start_station_id=val("start_station_id"),
            end_station_id=val("end_station_id"),
            start_lat=coord("start_lat"),
            start_lng=coord("start_lng"),
            end_lat=coord("end_lat"),
            end_lng=coord("end_lng"),
            source_file=self.path.name,
            loaded_at=datetime.now(UTC),
            rider_type=_RIDER_ALIASES.get(val("rider_type").lower()),
        )

    def collect(self) -> CollectionResult[TripRecord]:
        records: list[TripRecord] = []
        reasons: dict[str, int] = {}
        total = 0
        headers: list[str] = []

        for hdrs, row in self._iter_rows():
            headers = hdrs
            resolved = _resolve_aliases(hdrs)
            total += 1
            try:
                records.append(self._build_record(resolved, row, total))
            except (ValidationError, ValueError, KeyError) as exc:
                reason = _classify_error(exc)
                reasons[reason] = reasons.get(reason, 0) + 1

        excluded = sum(reasons.values())
        metadata = CollectionMetadata(
            collector=self.name,
            mode=self.mode,
            source=self.path.name,
            total_rows=total,
            accepted_rows=len(records),
            excluded_rows=excluded,
            exclusion_reasons=reasons,
            schema_hash=schema_hash_from_headers(headers) if headers else None,
            raw_payload_path=str(self.path),
        )
        return CollectionResult(records=records, metadata=metadata)
