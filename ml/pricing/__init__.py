"""Dynamic incentive & policy simulation (V1_Prompt §16).

Simulated only — there is no real interaction log, so every result carries ``is_simulated=true``
and the disclaimer. Credits are pickup/return incentives (>= 0), never a surcharge.
"""

from __future__ import annotations

from .scenario import ScenarioStation, build_demo_scenario
from .simulator import ChoiceSimulator, SimOutcome

__all__ = ["ScenarioStation", "build_demo_scenario", "ChoiceSimulator", "SimOutcome"]
