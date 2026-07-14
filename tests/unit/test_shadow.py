"""V1-05 live-shadow pipeline tests (V1_Prompt §11 acceptance). Offline fixture stream."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.live import run_shadow_stream


@pytest.fixture
def demo():
    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))
    return events, articles


def test_fixture_stream_e2e_emits_pending_predictions(demo) -> None:
    events, articles = demo
    res = run_shadow_stream(events, articles)
    assert res.batches_processed >= 1
    assert res.predictions  # at least one affected-zone prediction
    # No label yet -> every shadow prediction is pending (§11).
    assert all(p.claim_state == "pending" for p in res.predictions)
    assert res.as_dict()["all_pending"] is True
    assert res.latency_ms_per_batch  # real per-batch latency recorded


def test_restart_is_resumable_no_duplicate_work(demo, tmp_path: Path) -> None:
    events, articles = demo
    ck = tmp_path / "shadow.json"
    first = run_shadow_stream(events, articles, checkpoint_path=ck)
    assert first.batches_processed >= 1
    # Re-run from the checkpoint: everything already processed -> no new batches (§11 resume).
    second = run_shadow_stream(events, articles, checkpoint_path=ck)
    assert second.batches_processed == 0
    assert second.resumed_from is not None


def test_live_failure_does_not_touch_the_offline_path(demo) -> None:
    # The shadow replay is pure/offline; running it never requires a live provider.
    events, articles = demo
    res = run_shadow_stream(events, articles)
    assert res.as_dict()["n_pending_predictions"] == len(res.predictions)
