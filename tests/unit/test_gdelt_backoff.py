"""GDELT retry backoff (V1-01). CLAUDE.md §7.3, §17.

GDELT rate-limits bursty querying with HTTP 429. The provider must honour a ``Retry-After`` header,
otherwise back off exponentially for 429 (longer than a transient error) and cap the wait so a run
never hangs. Pure logic — no network.
"""

from __future__ import annotations

import urllib.error

from pipelines.collectors.backfill import (
    GdeltNewsProvider,
    _GdeltTextResponse,
    _looks_rate_limited,
)


def _provider() -> GdeltNewsProvider:
    return GdeltNewsProvider("q", enabled=False, backoff_s=8.0)


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError("http://x", code, "err", headers, None)  # type: ignore[arg-type]


def test_429_honours_retry_after_header() -> None:
    assert _provider()._retry_wait(_http_error(429, "30"), attempt=0) == 30.0


def test_429_retry_after_is_capped() -> None:
    assert _provider()._retry_wait(_http_error(429, "9999"), attempt=0) == 120.0


def test_429_without_header_backs_off_exponentially() -> None:
    p = _provider()
    assert p._retry_wait(_http_error(429), attempt=0) == 8.0
    assert p._retry_wait(_http_error(429), attempt=1) == 16.0
    assert p._retry_wait(_http_error(429), attempt=2) == 32.0
    assert p._retry_wait(_http_error(429), attempt=5) == 120.0  # 8*32 -> capped


def test_transient_error_uses_linear_backoff() -> None:
    p = _provider()
    assert p._retry_wait(urllib.error.URLError("boom"), attempt=0) == 8.0
    assert p._retry_wait(urllib.error.URLError("boom"), attempt=1) == 16.0


def test_non_429_http_error_uses_linear_backoff() -> None:
    assert _provider()._retry_wait(_http_error(503), attempt=1) == 16.0


def test_soft_rate_limit_text_backs_off_exponentially() -> None:
    # GDELT HTTP-200 text notice that reads like a rate limit → exponential (like a 429).
    p = _provider()
    err = _GdeltTextResponse("Your query is being rate limited. Please slow down.")
    assert p._retry_wait(err, attempt=0) == 8.0
    assert p._retry_wait(err, attempt=1) == 16.0
    assert p._retry_wait(err, attempt=4) == 120.0  # 8*16 -> capped


def test_non_rate_limit_text_uses_linear_backoff() -> None:
    # A non-JSON body that is NOT a rate-limit notice (e.g. out-of-range window) → linear.
    p = _provider()
    err = _GdeltTextResponse("No results found for the requested window.")
    assert p._retry_wait(err, attempt=0) == 8.0
    assert p._retry_wait(err, attempt=1) == 16.0


def test_looks_rate_limited_detects_notices() -> None:
    assert _looks_rate_limited("You are being RATE LIMITED")
    assert _looks_rate_limited("too many requests")
    assert _looks_rate_limited("request throttled")
    assert not _looks_rate_limited("no articles matched your query")


def test_reason_surfaces_gdelt_body() -> None:
    p = _provider()
    assert "rate-limit/notice" in p._reason(_GdeltTextResponse("rate limit exceeded"))
    assert "non-JSON body" in p._reason(_GdeltTextResponse("out of range window"))
    assert p._reason(_http_error(429)) == "HTTP 429 (rate limit)"
