"""V2-03 borough news-attribution tests.

The new piece in the borough re-measurement is ``build_news_llm_index``: attribute LLM-extracted
news events to boroughs by explicit name match, leakage-safe (features never precede the article's
``available_at``). These tests use a tiny synthetic news JSONL — no download, no network.
"""

from __future__ import annotations

import json

from ml.forecasting.llm_value_borough import _NEWS_COLS, build_news_llm_index


def _write_news(tmp_path, rows):
    p = tmp_path / "news.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_borough_attribution_and_leakage(tmp_path):
    # A transit-disruption article naming Manhattan, available 2026-06-10 08:00 ET.
    news = _write_news(tmp_path, [{
        "article_id": "n1",
        "title": "Subway signal failure snarls Manhattan commute",
        "text": "A signal failure disrupted subway service across Manhattan on Wednesday morning.",
        "source": "test",
        "published_at": "2026-06-10T08:00:00-04:00",
        "first_seen_at": "2026-06-10T08:00:00-04:00",
        "url_hash": "h1",
    }])
    idx, diag = build_news_llm_index(news)
    assert diag["attributed_articles"] == 1
    # Attributed to Manhattan.
    man_keys = [k for k in idx if k[0] == "Manhattan"]
    assert man_keys, "expected Manhattan borough-hour features"
    # Leakage-safety: no feature hour precedes availability (2026-06-10 08).
    assert min(k[1] for k in man_keys) >= "2026-06-10 08"
    # 24h relevance window from availability.
    assert max(k[1] for k in man_keys) <= "2026-06-11 08"
    # Transit flag set on the availability hour.
    assert idx[("Manhattan", "2026-06-10 08")]["news_llm_transit"] == 1.0


def test_article_without_borough_is_not_attributed(tmp_path):
    news = _write_news(tmp_path, [{
        "article_id": "n2",
        "title": "Statewide weather advisory issued",
        "text": "Rain expected across the region with no specific location named.",
        "source": "test",
        "published_at": "2026-06-10T08:00:00-04:00",
        "first_seen_at": "2026-06-10T08:00:00-04:00",
        "url_hash": "h2",
    }])
    idx, diag = build_news_llm_index(news)
    assert diag["attributed_articles"] == 0
    assert len(idx) == 0  # no borough named -> no fabricated attribution


def test_citywide_cue_attributes_all_boroughs(tmp_path):
    # A citywide subway disruption naming no single borough -> all 5 boroughs (documented rule).
    news = _write_news(tmp_path, [{
        "article_id": "n4",
        "title": "MTA subway signal failure disrupts service across the city",
        "text": "A signal failure caused citywide subway delays; no single area was spared.",
        "source": "test",
        "published_at": "2026-06-10T08:00:00-04:00",
        "first_seen_at": "2026-06-10T08:00:00-04:00",
        "url_hash": "h4",
    }])
    idx_on, diag_on = build_news_llm_index(news, citywide=True)
    boroughs = {k[0] for k in idx_on}
    assert boroughs == {"Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"}
    # With the rule off, no borough is named -> nothing attributed.
    idx_off, diag_off = build_news_llm_index(news, citywide=False)
    assert diag_off["attributed_articles"] == 0
    assert diag_on["attributed_articles"] == 1


def test_precomputed_claude_events_index(tmp_path):
    # Real-LLM path: events carry their own borough + type + severity; availability from the article.
    import json

    from ml.forecasting.llm_value_borough import build_news_llm_index_precomputed

    news = _write_news(tmp_path, [{
        "article_id": "x1", "title": "LIRR strike halts service", "text": "commuter rail shut down",
        "source": "t", "published_at": "2026-05-16T06:00:00-04:00",
        "first_seen_at": "2026-05-16T06:00:00-04:00", "url_hash": "h",
    }])
    ev = tmp_path / "claude_events.jsonl"
    ev.write_text(json.dumps({
        "article_id": "x1", "event_type": "TRANSIT_DISRUPTION",
        "boroughs": ["Manhattan", "Queens"], "severity": 0.8, "evidence": "shut down",
    }), encoding="utf-8")
    idx, diag = build_news_llm_index_precomputed(news, ev)
    assert diag["attributed_events"] == 1
    assert {k[0] for k in idx} == {"Manhattan", "Queens"}
    # Leakage: no feature before availability (2026-05-16 06); transit flag set.
    assert min(k[1] for k in idx) >= "2026-05-16 06"
    assert idx[("Manhattan", "2026-05-16 06")]["news_llm_transit"] == 1.0
    assert idx[("Manhattan", "2026-05-16 06")]["news_llm_severity"] == 0.8


def test_curated_claude_events_fixture_parses():
    # The committed real-LLM extraction fixture is valid and every row has the required fields.
    import json
    from pathlib import Path

    rows = [json.loads(l) for l in Path("data/fixtures/news_live/claude_events_2026h1.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) >= 20
    for r in rows:
        assert r["article_id"] and r["event_type"] and r["boroughs"]
        assert 0.0 <= r["severity"] <= 1.0
        assert r["extraction_model"] == "claude-opus-4-8-insession"


def test_news_feature_columns_present(tmp_path):
    news = _write_news(tmp_path, [{
        "article_id": "n3",
        "title": "Parade draws huge crowds in Brooklyn",
        "text": "A large public gathering and parade filled the streets of Brooklyn.",
        "source": "test",
        "published_at": "2026-05-01T10:00:00-04:00",
        "first_seen_at": "2026-05-01T10:00:00-04:00",
        "url_hash": "h3",
    }])
    idx, _ = build_news_llm_index(news)
    bk = next(k for k in idx if k[0] == "Brooklyn")
    for c in _NEWS_COLS:
        assert c in idx[bk]
