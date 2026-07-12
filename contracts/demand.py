"""Demand panel contract. CLAUDE.md sections 4 and 6.

One aggregated demand cell at the primary grain: H3 zone x local hour. Targets are
departures, arrivals, and net_flow = arrivals - departures.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from .common import ContractModel
from .enums import OperatingMode


class DemandCell(ContractModel):
    zone_id: str = Field(min_length=1, description="H3 cell id.")
    hour_start: AwareDatetime = Field(
        description="Start of the local-hour bucket (timezone-aware, America/New_York)."
    )
    departures: int = Field(ge=0)
    arrivals: int = Field(ge=0)
    net_flow: int
    # Departure composition by membership class (0 when rider type is unknown).
    departures_member: int = Field(default=0, ge=0)
    departures_casual: int = Field(default=0, ge=0)
    mode: OperatingMode

    @model_validator(mode="after")
    def _check_invariants(self) -> DemandCell:
        if self.net_flow != self.arrivals - self.departures:
            raise ValueError("net_flow must equal arrivals - departures")
        if self.departures_member + self.departures_casual > self.departures:
            raise ValueError("departures_member + departures_casual cannot exceed departures")
        return self
