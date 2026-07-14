"""Clustered-switchback experimentation (V1_Prompt §17). Simulated only — never a causal lift."""

from __future__ import annotations

from .engine import ExperimentResult, run_experiment
from .switchback import cluster_zones, switchback_assignment

__all__ = ["cluster_zones", "switchback_assignment", "ExperimentResult", "run_experiment"]
