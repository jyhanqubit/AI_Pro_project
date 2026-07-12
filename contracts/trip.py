"""Trip record contract. CLAUDE.md section 6.1.

The model is strict: invalid trips raise. Pipelines catch these and record excluded
row counts and reasons in metadata rather than silently discarding them (section 6.1).
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from .common import ContractModel
from .enums import RiderType


class TripRecord(ContractModel):
    trip_id: str = Field(min_length=1, description="Trip id or deterministic row key.")
    started_at: AwareDatetime
    ended_at: AwareDatetime
    start_station_id: str = Field(min_length=1)
    end_station_id: str = Field(min_length=1)
    start_lat: float = Field(ge=-90.0, le=90.0)
    start_lng: float = Field(ge=-180.0, le=180.0)
    end_lat: float = Field(ge=-90.0, le=90.0)
    end_lng: float = Field(ge=-180.0, le=180.0)
    source_file: str = Field(min_length=1)
    loaded_at: AwareDatetime
    # Optional migration field (backward-compatible): membership class when known.
    rider_type: RiderType | None = None

    @model_validator(mode="after")
    def _end_not_before_start(self) -> TripRecord:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not be before started_at")
        return self
