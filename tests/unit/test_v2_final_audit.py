"""V2-09 final audit — the completion gate must pass on the committed repo, and it must actually
catch a mislabeled artifact (not just rubber-stamp)."""

from __future__ import annotations

import json

from scripts.v2_final_audit import (
    COMPLETION_ARTIFACTS,
    gate_completion,
    gate_envelopes,
    gate_traceability,
)


def test_all_committed_artifacts_have_valid_envelopes():
    rows, problems = gate_envelopes()
    assert not problems, f"envelope problems: {problems}"
    assert len(rows) >= 20  # the V2 artifact set
    # research artifacts must only be in research mode (spot-check the contract holds in the data)
    for r in rows:
        if r["claim_status"] == "research":
            assert r["mode"] == "research"
        if r["claim_status"] == "demo_fixture":
            assert r["mode"] == "demo_fixture"


def test_completion_and_traceability_gates_pass():
    rows, _ = gate_envelopes()
    assert not gate_completion(rows)
    assert not gate_traceability(rows)


def test_every_completion_artifact_exists():
    from scripts.v2_final_audit import REPO_ROOT

    for claim, rel in COMPLETION_ARTIFACTS.items():
        if rel == "reports/v2/final/claim_matrix.json":
            continue  # produced by the run itself
        assert (REPO_ROOT / rel).exists(), f"missing {claim}: {rel}"


def test_envelope_gate_catches_a_mislabel(tmp_path, monkeypatch):
    """Drop a mislabeled artifact (research status in live mode) and confirm the gate fails it."""
    import scripts.v2_final_audit as mod

    fake_reports = tmp_path / "reports" / "v2" / "bad"
    fake_reports.mkdir(parents=True)
    (fake_reports / "mislabel.json").write_text(
        json.dumps(
            {
                "run_id": "run_bad",
                "artifact_id": "reports/v2/bad/mislabel.json",
                "mode": "live",
                "claim_status": "research",  # research allowed only in research mode
                "freshness": "2026-07-22T00:00:00+00:00",
            }
        )
    )
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "V2_REPORTS", tmp_path / "reports" / "v2")
    monkeypatch.setattr(mod, "CLAIM_MATRIX", tmp_path / "reports/v2/final/claim_matrix.json")
    _, problems = gate_envelopes()
    assert any("mislabel.json" in p for p in problems), problems
