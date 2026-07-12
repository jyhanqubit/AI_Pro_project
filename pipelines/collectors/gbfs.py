"""GBFS station_status collector. CLAUDE.md sections 7.3, 6, 3.

Fixture mode is mandatory and offline. Live mode is optional and disabled by default;
a live failure returns a degraded result (empty records + warning) and never raises,
so it cannot break Demo Mode. Live fetching uses a bounded retry with a request timeout.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from config.collectors import (
    GBFS_LIVE_MAX_RETRIES,
    GBFS_LIVE_TIMEOUT_SECONDS,
    GBFS_STATION_STATUS_URL,
)
from contracts.enums import OperatingMode
from contracts.station import StationStatusRecord

from .base import CollectionMetadata, CollectionResult, Collector, sha256_hex


def _epoch_to_utc(seconds: int | float | None) -> datetime | None:
    if seconds is None:
        return None
    return datetime.fromtimestamp(float(seconds), tz=UTC)


def _parse_payload(
    raw_bytes: bytes, *, mode: OperatingMode, source: str, raw_payload_path: str
) -> list[StationStatusRecord]:
    payload = json.loads(raw_bytes)
    fetched_at = datetime.now(UTC)
    payload_hash = sha256_hex(raw_bytes)
    source_last_updated = _epoch_to_utc(payload.get("last_updated")) or fetched_at

    records: list[StationStatusRecord] = []
    for station in payload.get("data", {}).get("stations", []):
        records.append(
            StationStatusRecord(
                station_id=str(station["station_id"]),
                num_bikes_available=int(station.get("num_bikes_available", 0)),
                num_docks_available=int(station.get("num_docks_available", 0)),
                is_installed=bool(station.get("is_installed", 0)),
                is_renting=bool(station.get("is_renting", 0)),
                is_returning=bool(station.get("is_returning", 0)),
                last_reported=_epoch_to_utc(station.get("last_reported")),
                source_last_updated=source_last_updated,
                fetched_at=fetched_at,
                payload_hash=payload_hash,
                raw_payload_path=raw_payload_path,
                mode=mode,
            )
        )
    return records


class GbfsStationStatusCollector(Collector[StationStatusRecord]):
    name = "gbfs_station_status"

    def __init__(
        self,
        fixture_path: str | Path,
        *,
        live: bool = False,
        url: str = GBFS_STATION_STATUS_URL,
        timeout: float = GBFS_LIVE_TIMEOUT_SECONDS,
        max_retries: int = GBFS_LIVE_MAX_RETRIES,
    ) -> None:
        self.fixture_path = Path(fixture_path)
        self.live = live
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries

    def _collect_fixture(self) -> CollectionResult[StationStatusRecord]:
        raw_bytes = self.fixture_path.read_bytes()
        records = _parse_payload(
            raw_bytes,
            mode=OperatingMode.DEMO_FIXTURE,
            source=self.fixture_path.name,
            raw_payload_path=str(self.fixture_path),
        )
        metadata = CollectionMetadata(
            collector=self.name,
            mode=OperatingMode.DEMO_FIXTURE,
            source=self.fixture_path.name,
            total_rows=len(records),
            accepted_rows=len(records),
            payload_hash=sha256_hex(raw_bytes),
            raw_payload_path=str(self.fixture_path),
        )
        return CollectionResult(records=records, metadata=metadata)

    def _collect_live(self) -> CollectionResult[StationStatusRecord]:
        last_error: str | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urlopen(self.url, timeout=self.timeout) as resp:  # noqa: S310 (trusted URL)
                    raw_bytes = resp.read()
                records = _parse_payload(
                    raw_bytes,
                    mode=OperatingMode.LIVE,
                    source=self.url,
                    raw_payload_path=self.url,
                )
                metadata = CollectionMetadata(
                    collector=self.name,
                    mode=OperatingMode.LIVE,
                    source=self.url,
                    total_rows=len(records),
                    accepted_rows=len(records),
                    payload_hash=sha256_hex(raw_bytes),
                    raw_payload_path=self.url,
                )
                return CollectionResult(records=records, metadata=metadata)
            except (URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
                last_error = f"attempt {attempt}/{self.max_retries}: {exc}"

        # Degraded state: never corrupt stored state or stop Demo Mode (section 7.3).
        metadata = CollectionMetadata(
            collector=self.name,
            mode=OperatingMode.LIVE,
            source=self.url,
            warnings=[f"live GBFS fetch failed and returned degraded state ({last_error})"],
        )
        return CollectionResult(records=[], metadata=metadata)

    def collect(self) -> CollectionResult[StationStatusRecord]:
        if self.live:
            return self._collect_live()
        return self._collect_fixture()
