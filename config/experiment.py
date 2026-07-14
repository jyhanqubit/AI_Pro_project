"""Clustered-switchback experimentation configuration (V1_Prompt §17).

Randomisation unit = zone-cluster × time-block (respects shared-inventory interference). Without
real users, experiments are **simulated** — outcomes come from the policy choice simulator and are
never presented as a real causal lift (invariant 9/10). No RL/bandit on the required path.
"""

from __future__ import annotations

from dataclasses import dataclass

EXPERIMENT_CONFIG_VERSION = "experiment-v1"


@dataclass(frozen=True)
class ExperimentConfig:
    n_clusters: int = 3  # zone clusters
    n_time_blocks: int = 8  # switchback blocks over the horizon
    washout_blocks: int = 1  # leading blocks dropped from analysis (carryover)
    srm_tolerance: float = 0.2  # max |observed - 0.5| assignment share before SRM flags
    bootstrap_samples: int = 500  # cluster block-bootstrap for the CI
    alpha: float = 0.05  # 95% CI
    # Deterministic per-time-block demand heterogeneity so units vary (simulated).
    demand_jitter: float = 0.35
    seed: int = 42
    version: str = EXPERIMENT_CONFIG_VERSION
