"""V1-08 clustered-switchback experimentation tests (V1_Prompt §17 acceptance)."""

from __future__ import annotations

import pytest

from config.experiment import ExperimentConfig
from config.pricing import POLICIES, PolicySpec
from ml.experiment.engine import run_experiment
from ml.experiment.switchback import assignment_shares, cluster_zones, switchback_assignment
from ml.pricing.scenario import build_demo_scenario

_P = {p.key: p for p in POLICIES}
_CFG = ExperimentConfig(n_clusters=4, n_time_blocks=10)


@pytest.fixture
def stations():
    return build_demo_scenario()


def test_clustering_and_assignment_are_deterministic() -> None:
    zones = ["z1", "z2", "z3", "z4"]
    assert cluster_zones(zones, 3, 42) == cluster_zones(zones, 3, 42)
    a1 = switchback_assignment(["c0", "c1"], 6, ("control", "treatment"), 42)
    a2 = switchback_assignment(["c0", "c1"], 6, ("control", "treatment"), 42)
    assert a1 == a2


def test_assignment_is_balanced_no_srm() -> None:
    assign = switchback_assignment([f"c{i}" for i in range(4)], 10, ("control", "treatment"), 42)
    shares = assignment_shares(assign, ("control", "treatment"))
    assert shares["control"] == pytest.approx(0.5)
    assert shares["treatment"] == pytest.approx(0.5)


def test_aa_effect_is_null_ci_contains_zero(stations) -> None:
    aa = run_experiment("AA", "A/A", stations, {"control": _P["P0"], "treatment": _P["P0"]}, _CFG)
    assert aa.srm_ok
    assert aa.itt_ci[0] <= 0.0 <= aa.itt_ci[1]  # A/A must not be a false positive
    assert abs(aa.itt_effect) < 0.1


def test_treatment_shows_detectable_simulated_effect(stations) -> None:
    arms = {"control": _P["P0"], "treatment": _P["P5"]}
    hyb = run_experiment("HYB", "hybrid", stations, arms, _CFG)
    assert hyb.itt_effect > 0  # hybrid fulfils more demand (simulated)
    assert hyb.itt_ci[0] > 0.0  # CI excludes zero -> detectable in this simulation


def test_all_results_labelled_simulated(stations) -> None:
    r = run_experiment("X", "h", stations, {"control": _P["P0"], "treatment": _P["P3"]}, _CFG)
    assert r.is_simulated is True
    assert r.status == "simulated_experiment"
    assert "SIMULATED OUTCOME" in r.disclaimer
    assert "not a real causal lift" in r.note.lower()


def test_logs_and_propensity_recorded(stations) -> None:
    r = run_experiment("X", "h", stations, {"control": _P["P0"], "treatment": _P["P3"]}, _CFG)
    assert len(r.exposure_logs) == r.n_units
    assert len(r.outcome_logs) == r.n_units
    assert all(e.propensity == 0.5 for e in r.exposure_logs)  # known balanced propensity


def test_requires_exactly_two_arms(stations) -> None:
    with pytest.raises(ValueError, match="two arms"):
        run_experiment("X", "h", stations, {"only": _P["P0"]}, _CFG)


def test_recommendation_only_arm_runs(stations) -> None:
    rec = PolicySpec("REC", "Recommendation only", recommend=True)
    r = run_experiment("REC", "rec-only", stations, {"control": _P["P0"], "treatment": rec}, _CFG)
    assert r.n_units > 0 and r.is_simulated
