"""V2-07 — the cockpit metrics surface must resolve every number to a committed artifact.

Guards the core V2-07 contract: no hard-coded UI metrics. For each surfaced metric we re-read the
value straight from its artifact file and assert the envelope matches — so a number can never drift
from (or be faked relative to) the artifact it claims to come from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts.enums import OperatingMode
from services.api.v2_metrics import cockpit_metrics


def _resolve(artifact_id: str):
    """Follow 'path.json#a.b.c' to the value actually stored in the artifact."""
    path, _, pointer = artifact_id.partition("#")
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if not pointer:
        return d
    for key in pointer.split("."):
        d = d[key]
    return d


def test_every_metric_resolves_to_its_artifact_no_hardcoding():
    metrics = cockpit_metrics(OperatingMode.HISTORICAL_REPLAY)
    assert metrics, "cockpit produced no metrics"
    for m in metrics:
        env = m["envelope"]
        if env["claim_status"] == "blocked_data":
            continue  # a genuinely missing artifact surfaces blocked, value None — allowed
        aid = env["artifact_id"]
        assert aid, f"{m['key']}: measured/simulated metric must cite an artifact_id"
        assert Path(aid.split('#', 1)[0]).exists(), f"{m['key']}: artifact file missing ({aid})"
        stored = _resolve(aid)
        val = env["value"]
        # numbers must match the artifact within rounding; strings/exact must equal
        if isinstance(val, (int, float)) and isinstance(stored, (int, float)):
            assert abs(float(val) - float(stored)) <= 0.5 + abs(float(stored)) * 1e-3, \
                f"{m['key']}: envelope value {val} != artifact value {stored}"
        elif m["key"] == "best_policy":
            assert isinstance(stored, list) and val in stored  # ranking list; value is a member
        else:
            assert str(val) == str(stored), f"{m['key']}: {val} != {stored}"


def test_research_status_never_on_a_product_surface():
    # research (e.g. synthetic ceiling) must never leak into a non-research cockpit.
    for m in cockpit_metrics(OperatingMode.HISTORICAL_REPLAY):
        assert m["envelope"]["claim_status"] != "research"


def test_measured_metrics_carry_runid_and_freshness():
    for m in cockpit_metrics(OperatingMode.HISTORICAL_REPLAY):
        env = m["envelope"]
        if env["claim_status"] == "blocked_data":
            continue
        assert env["run_id"] and env["run_id"] != "unknown", f"{m['key']}: missing run_id"
        assert env["freshness"], f"{m['key']}: missing freshness"
        assert env["mode"] == "historical_replay"


def test_core_measured_metrics_present():
    keys = {m["key"] for m in cockpit_metrics(OperatingMode.HISTORICAL_REPLAY)}
    assert {"forecast_wape", "promoted_model", "best_policy"} <= keys
