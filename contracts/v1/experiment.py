"""Clustered-switchback experimentation contracts (V1_Prompt §17).

Randomisation unit is a (zone-cluster × time-block) to respect shared-inventory interference.
Results are labelled actual / simulated / dry-run and are never called a real causal lift unless
a real randomized experiment with real users produced them.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from contracts.common import ContractModel

from .enums import OperatingModeV1


class ExperimentStatus(StrEnum):
    ACTUAL_EXPERIMENT = "actual_experiment"
    SIMULATED_EXPERIMENT = "simulated_experiment"
    EXPERIMENT_DRY_RUN = "experiment_dry_run"


class ExperimentDefinition(ContractModel):
    experiment_id: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    randomization_unit: str = Field(
        default="zone_cluster_x_time_block", description="Clustered switchback (§17)."
    )
    arms: list[str] = Field(min_length=2)
    washout_minutes: int = Field(ge=0, default=0)
    seed: int
    status: ExperimentStatus
    created_at: AwareDatetime
    mode: OperatingModeV1


class ExposureLog(ContractModel):
    experiment_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1, description="zone_cluster:time_block key.")
    arm: str = Field(min_length=1)
    assigned_at: AwareDatetime
    propensity: float | None = Field(default=None, ge=0.0, le=1.0)


class OutcomeLog(ContractModel):
    experiment_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    arm: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    metric_value: float
    observed_at: AwareDatetime
    is_simulated: bool = Field(
        default=True, description="True unless a real experiment produced the outcome (§17)."
    )
