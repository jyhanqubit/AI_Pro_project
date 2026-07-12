"""GBFS station-status contract. CLAUDE.md sections 2 (MVP source 3) and 7.3.

Current station inventory and operating state, carrying the provenance fields required
by section 7.3: fetched_at, source update time, payload hash, and raw payload path.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field

from .common import ContractModel
from .enums import OperatingMode


class StationStatusRecord(ContractModel):
    station_id: str = Field(min_length=1)
    num_bikes_available: int = Field(ge=0)
    num_docks_available: int = Field(ge=0)
    is_installed: bool
    is_renting: bool
    is_returning: bool
    last_reported: AwareDatetime | None = Field(
        default=None, description="Per-station last report time from the feed."
    )

    # Provenance (section 7.3)
    source_last_updated: AwareDatetime = Field(description="Feed-level last_updated time.")
    fetched_at: AwareDatetime = Field(description="When the collector fetched the payload.")
    payload_hash: str = Field(min_length=1)
    raw_payload_path: str = Field(min_length=1)
    mode: OperatingMode
