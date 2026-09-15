"""V2-08 — run manifest coverage + the delayed-label leakage guard (the phase's key acceptance)."""

from __future__ import annotations

from datetime import UTC, datetime

from ml.monitoring.delayed_labels import ArrivedLabel, PendingForecast, resolve
from ml.monitoring.run_manifest import build, scan


def _h(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def test_manifest_indexes_every_v2_artifact_with_run_id():
    rows = scan(datetime.now(UTC))
    assert rows, "no artifacts scanned"
    # every measured/simulated/offline result must carry a run_id (provenance)
    for r in rows:
        if r["claim_status"] in {"measured", "simulated", "offline_benchmark"}:
            assert r["has_run_id"], f"{r['artifact']} missing run_id"


def test_manifest_summary_counts_are_consistent():
    rep = build(datetime.now(UTC))
    assert rep["n_artifacts"] == len(rep["artifacts"])
    assert rep["with_run_id"] <= rep["n_artifacts"]
    assert sum(rep["by_claim_status"].values()) <= rep["n_artifacts"]
    assert rep["claim_status"] == "measured"


def test_delayed_label_closes_only_when_available_after_cutoff():
    cutoff = _h("2026-05-01T14:00")
    target = _h("2026-05-01T18:00")
    pending = [PendingForecast("Z", cutoff, target, 30.0)]
    # label available AFTER the forecast was made -> valid close
    ok = resolve(pending, [ArrivedLabel("Z", target, 33.0, _h("2026-05-01T19:00"))])
    assert ok["n_closed_measured"] == 1 and ok["n_leakage_rejected"] == 0
    assert ok["closed"][0]["claim_status"] == "measured"


def test_delayed_label_rejects_leak_available_at_or_before_cutoff():
    cutoff = _h("2026-05-01T14:00")
    target = _h("2026-05-01T18:00")
    pending = [PendingForecast("Z", cutoff, target, 30.0)]
    # label "available" BEFORE the cutoff -> would leak -> must be rejected, forecast stays pending
    leaky = resolve(pending, [ArrivedLabel("Z", target, 33.0, _h("2026-05-01T13:00"))])
    assert leaky["n_closed_measured"] == 0
    assert leaky["n_leakage_rejected"] == 1
    assert leaky["n_still_pending"] == 1
    # exactly-at-cutoff is also a leak (strict >)
    at = resolve(pending, [ArrivedLabel("Z", target, 33.0, cutoff)])
    assert at["n_closed_measured"] == 0 and at["n_leakage_rejected"] == 1


def test_delayed_label_unmatched_stays_pending():
    cutoff = _h("2026-05-01T14:00")
    target = _h("2026-05-01T18:00")
    pending = [PendingForecast("Z", cutoff, target, 30.0)]
    none = resolve(pending, [])
    assert none["n_closed_measured"] == 0 and none["n_still_pending"] == 1
    assert none["still_pending"][0]["reason"] == "no_label_yet"
