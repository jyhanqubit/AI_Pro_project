"""V1-01 news backfill + coverage-gate tests (V1_Prompt §7 acceptance)."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.backfill import BackfillConfig
from pipelines.collectors.backfill import (
    FixtureNewsProvider,
    GdeltNewsProvider,
    ProviderUnavailable,
    backfill_news,
    title_hash,
)
from pipelines.collectors.coverage import coverage_gate, coverage_report

_ROOT = Path(__file__).resolve().parents[2]
_NEWS = _ROOT / "data" / "fixtures" / "news_demo.jsonl"


def _cfg() -> BackfillConfig:
    return BackfillConfig()


def test_fixture_provider_reads_articles() -> None:
    raw = FixtureNewsProvider(_NEWS).fetch()
    assert len(raw) >= 3
    assert all("title" in r for r in raw)


def test_backfill_accepts_and_filters(tmp_path: Path) -> None:
    ck = tmp_path / "news.json"
    res = backfill_news(FixtureNewsProvider(_NEWS), _cfg(), checkpoint_path=ck)
    assert res.report.accepted_count > 0
    assert res.report.candidate_count >= res.report.accepted_count
    # Articles come back ordered by availability.
    avails = [a.available_at for a in res.articles]
    assert avails == sorted(avails)
    assert ck.exists()  # checkpoint persisted


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    ck = tmp_path / "news.json"
    first = backfill_news(FixtureNewsProvider(_NEWS), _cfg(), checkpoint_path=ck)
    second = backfill_news(FixtureNewsProvider(_NEWS), _cfg(), checkpoint_path=ck)
    assert first.report.accepted_count > 0
    assert second.report.accepted_count == 0  # all already seen -> no duplicates (§7)


def test_title_hash_dedup(tmp_path: Path) -> None:
    fixture = tmp_path / "dup.jsonl"
    line = (
        '{{"article_id":"{aid}","title":"PATH signal failure at Hoboken","text":"transit",'
        '"source":"wire","published_at":"2026-07-12T14:00:00-04:00",'
        '"first_seen_at":"2026-07-12T14:00:00-04:00","url_hash":"{uh}"}}'
    )
    fixture.write_text(
        line.format(aid="x1", uh="u1") + "\n" + line.format(aid="x2", uh="u2") + "\n",
        encoding="utf-8",
    )
    res = backfill_news(FixtureNewsProvider(fixture), _cfg(), checkpoint_path=tmp_path / "c.json")
    assert res.report.accepted_count == 1  # same normalised title -> deduped
    assert res.report.excluded.get("duplicate", 0) == 1


def test_gdelt_disabled_is_degraded_not_fabricated(tmp_path: Path) -> None:
    res = backfill_news(
        GdeltNewsProvider(enabled=False), _cfg(), checkpoint_path=tmp_path / "g.json"
    )
    assert res.report.degraded is True
    assert res.report.accepted_count == 0  # no fabricated articles
    with pytest.raises(ProviderUnavailable):
        GdeltNewsProvider(enabled=False).fetch()


def test_coverage_report_and_gate(tmp_path: Path) -> None:
    res = backfill_news(FixtureNewsProvider(_NEWS), _cfg(), checkpoint_path=tmp_path / "c.json")
    rep = coverage_report(res.report)
    # Article-level fields populated; event/feature fields null until V1-02+ (not fabricated).
    assert rep.accepted_count == res.report.accepted_count
    assert rep.unique_event_cluster_count is None
    assert rep.non_zero_feature_ratio_by_split is None
    gate = coverage_gate(rep, _cfg())
    assert gate.passed is True


def test_gate_fails_when_degraded(tmp_path: Path) -> None:
    res = backfill_news(
        GdeltNewsProvider(enabled=False), _cfg(), checkpoint_path=tmp_path / "g.json"
    )
    gate = coverage_gate(coverage_report(res.report), _cfg())
    assert gate.passed is False
    assert any("degraded" in r for r in gate.reasons)


def test_normalised_title_hash_is_stable() -> None:
    assert title_hash("  PATH  Signal  Failure ") == title_hash("path signal failure")
