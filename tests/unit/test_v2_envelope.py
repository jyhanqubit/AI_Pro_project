"""V2 result-envelope contract tests (V2-00).

Locks in the honesty rules the envelope enforces in code (CLAUDE_V2_APPEND_REVISED.md → Claims,
Productization; docs/v2/V2_CLAIMS_MATRIX.md): traceability fields are required, freshness is
timezone-aware, evidence-free numbers cannot leave demo mode, demo/research statuses are
mode-bound, and blocked/pending results carry no fabricated value.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from contracts.enums import OperatingMode
from contracts.v2 import ClaimStatus, ResultEnvelope, claimstate_to_status

FRESH = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _env(**overrides):
    base = dict(
        value=0.42,
        run_id="run_abc",
        artifact_id="reports/v2/holdout/h3_multiholdout.json#aggregate.wape",
        mode=OperatingMode.HISTORICAL_REPLAY,
        claim_status=ClaimStatus.MEASURED,
        freshness=FRESH,
    )
    base.update(overrides)
    return base


def test_measured_result_with_artifact_is_valid():
    env = ResultEnvelope(**_env())
    assert env.value == 0.42
    assert env.is_product_decisionable is True


def test_freshness_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        ResultEnvelope(**_env(freshness=datetime(2026, 7, 20, 12, 0)))  # naive


def test_run_id_is_required_nonempty():
    with pytest.raises(ValidationError):
        ResultEnvelope(**_env(run_id=""))


def test_measured_value_outside_demo_requires_artifact():
    with pytest.raises(ValidationError):
        ResultEnvelope(**_env(artifact_id=None))


def test_demo_fixture_value_needs_no_artifact():
    env = ResultEnvelope(
        **_env(mode=OperatingMode.DEMO_FIXTURE, claim_status=ClaimStatus.DEMO_FIXTURE, artifact_id=None)
    )
    assert env.artifact_id is None
    assert env.is_product_decisionable is False


def test_demo_fixture_status_only_in_demo_mode():
    with pytest.raises(ValidationError):
        ResultEnvelope(**_env(claim_status=ClaimStatus.DEMO_FIXTURE, mode=OperatingMode.LIVE))


def test_research_status_only_in_research_mode():
    with pytest.raises(ValidationError):
        ResultEnvelope(**_env(claim_status=ClaimStatus.RESEARCH, mode=OperatingMode.LIVE))


def test_research_status_in_research_mode_ok():
    env = ResultEnvelope(
        **_env(claim_status=ClaimStatus.RESEARCH, mode=OperatingMode.RESEARCH)
    )
    assert env.claim_status is ClaimStatus.RESEARCH


@pytest.mark.parametrize(
    "status",
    [ClaimStatus.BLOCKED_DATA, ClaimStatus.BLOCKED_EXTERNAL, ClaimStatus.PENDING_LIVE_LABEL],
)
def test_blocked_or_pending_must_not_carry_value(status):
    with pytest.raises(ValidationError):
        ResultEnvelope(**_env(claim_status=status, value=0.42, artifact_id=None))


@pytest.mark.parametrize(
    "status",
    [ClaimStatus.BLOCKED_DATA, ClaimStatus.BLOCKED_EXTERNAL, ClaimStatus.PENDING_LIVE_LABEL],
)
def test_blocked_or_pending_with_none_value_ok(status):
    env = ResultEnvelope(**_env(claim_status=status, value=None, artifact_id=None))
    assert env.value is None


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        ResultEnvelope(**_env(unexpected="x"))


def test_all_nine_claim_statuses_present():
    assert {s.value for s in ClaimStatus} == {
        "measured",
        "offline_benchmark",
        "simulated",
        "pending_live_label",
        "assumption",
        "blocked_data",
        "blocked_external",
        "demo_fixture",
        "research",
    }


@pytest.mark.parametrize(
    "v1_state,expected",
    [
        ("measured", ClaimStatus.MEASURED),
        ("pending", ClaimStatus.PENDING_LIVE_LABEL),
        ("simulated", ClaimStatus.SIMULATED),
        ("dry_run", ClaimStatus.SIMULATED),
        ("research", ClaimStatus.RESEARCH),
    ],
)
def test_v1_claimstate_migration(v1_state, expected):
    assert claimstate_to_status(v1_state) is expected


def test_v1_claimstate_migration_unknown_fails_loudly():
    with pytest.raises(ValueError):
        claimstate_to_status("bogus")
