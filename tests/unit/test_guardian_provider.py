"""Guardian news provider (§7, §7.4). Pure logic — no network.

Verifies the permitted-snippet HTML stripping, payload mapping (real provenance, no fabrication),
retry/backoff math, key/enable gating, and pagination without touching the internet (§17).
"""

from __future__ import annotations

import urllib.error

import pytest

from pipelines.collectors.backfill import ProviderUnavailable
from pipelines.collectors.guardian_provider import GuardianNewsProvider, strip_html


def _provider(**kw) -> GuardianNewsProvider:
    kw.setdefault("api_key", "test-key")
    kw.setdefault("enabled", True)
    return GuardianNewsProvider("nyc bikes", **kw)


def test_strip_html_removes_tags_entities_and_collapses_ws() -> None:
    assert strip_html("<strong>Subway</strong>  &amp;  <a>bikes</a>") == "Subway & bikes"
    assert strip_html("") == ""


def test_disabled_provider_degrades() -> None:
    with pytest.raises(ProviderUnavailable):
        GuardianNewsProvider("q", api_key="k", enabled=False).fetch()


def test_missing_key_degrades() -> None:
    with pytest.raises(ProviderUnavailable, match="key"):
        GuardianNewsProvider("q", api_key=None, enabled=True).fetch()


def test_url_carries_key_query_and_dates() -> None:
    p = _provider(from_date="2026-01-01", to_date="2026-02-01")
    url = p._url(2)
    assert "api-key=test-key" in url
    assert "from-date=2026-01-01" in url and "to-date=2026-02-01" in url
    assert "page=2" in url and "show-fields=trailText" in url


def test_to_payload_is_real_provenance() -> None:
    a = {
        "webUrl": "https://www.theguardian.com/us-news/2026/jan/15/nyc-subway",
        "webTitle": "NYC subway signal failure snarls commute",
        "webPublicationDate": "2026-01-15T13:04:22Z",
        "fields": {"trailText": "<strong>Delays</strong> across Manhattan lines"},
    }
    p = GuardianNewsProvider._to_payload(a)
    assert p["title"] == "NYC subway signal failure snarls commute"
    assert p["text"] == "Delays across Manhattan lines"  # snippet stripped, not fabricated
    assert p["source"] == "theguardian.com"
    assert p["published_at"] == p["first_seen_at"] == "2026-01-15T13:04:22Z"
    assert p["url"] == a["webUrl"] and len(p["url_hash"]) == 64


def test_429_backs_off_exponentially_and_caps() -> None:
    p = _provider(backoff_s=5.0)
    err = urllib.error.HTTPError("http://x", 429, "rl", {}, None)  # type: ignore[arg-type]
    assert p._retry_wait(err, attempt=0) == 5.0
    assert p._retry_wait(err, attempt=1) == 10.0
    assert p._retry_wait(err, attempt=6) == 120.0  # capped


def test_429_honours_retry_after() -> None:
    p = _provider(backoff_s=5.0)
    err = urllib.error.HTTPError("http://x", 429, "rl", {"Retry-After": "42"}, None)  # type: ignore[arg-type]
    assert p._retry_wait(err, attempt=3) == 42.0


def _result(url: str, title: str) -> dict:
    return {"webUrl": url, "webTitle": title, "webPublicationDate": "2026-01-01T00:00:00Z"}


def test_fetch_paginates_and_stops_at_last_page(monkeypatch) -> None:
    pages = {
        1: {"pages": 2, "results": [_result("u1", "t1")]},
        2: {"pages": 2, "results": [_result("u2", "t2")]},
    }
    p = _provider(max_pages=5)
    monkeypatch.setattr(p, "_fetch_page", lambda page: pages[page])
    out = p.fetch()
    assert [a["title"] for a in out] == ["t1", "t2"]  # stopped at page 2 of 2


def test_fetch_respects_max_pages(monkeypatch) -> None:
    p = _provider(max_pages=1)
    calls: list[int] = []

    def fake(page: int) -> dict:
        calls.append(page)
        return {"pages": 9, "results": [_result(f"u{page}", "t")]}

    monkeypatch.setattr(p, "_fetch_page", fake)
    p.fetch()
    assert calls == [1]  # never went past max_pages
