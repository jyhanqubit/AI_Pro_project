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
        GdeltNewsProvider("test query", enabled=False), _cfg(), checkpoint_path=tmp_path / "g.json"
    )
    assert res.report.degraded is True
    assert res.report.accepted_count == 0  # no fabricated articles
    with pytest.raises(ProviderUnavailable):
        GdeltNewsProvider("test query", enabled=False).fetch()


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
        GdeltNewsProvider("test query", enabled=False), _cfg(), checkpoint_path=tmp_path / "g.json"
    )
    gate = coverage_gate(coverage_report(res.report), _cfg())
    assert gate.passed is False
    assert any("degraded" in r for r in gate.reasons)


def test_normalised_title_hash_is_stable() -> None:
    assert title_hash("  PATH  Signal  Failure ") == title_hash("path signal failure")


# --- GDELT provider: offline-only checks (no network; unit tests must not hit the internet) ------
def test_gdelt_url_and_query_build() -> None:
    p = GdeltNewsProvider("Hoboken PATH", enabled=True, start="20260601000000", max_records=50)
    url = p._url()
    assert url.startswith("https://api.gdeltproject.org/api/v2/doc/doc?")
    assert "maxrecords=50" in url and "format=json" in url and "startdatetime=20260601000000" in url


def test_gdelt_payload_mapping_is_title_only_no_fabrication() -> None:
    raw = {
        "url": "https://example.com/a", "title": "PATH service change at Hoboken",
        "domain": "example.com", "seendate": "20260612T131500Z",
    }
    pl = GdeltNewsProvider._to_payload(raw)
    assert pl["text"] == ""  # GDELT gives no body -> empty, never fabricated
    assert pl["source"] == "example.com"
    assert pl["published_at"] == pl["first_seen_at"]  # seendate used for both (documented)
    assert pl["published_at"].startswith("2026-06-12T13:15:00")
    assert len(pl["url_hash"]) == 64
