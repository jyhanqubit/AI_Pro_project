"""Real news provider: The Guardian Open Platform Content API (CLAUDE.md §7, §7.4).

The Guardian's Content API is a genuine, crawlable source with a **full historical archive**
(1999→present) — unlike GDELT DOC 2.0 which only serves roughly the last few months. It needs a
free developer key (instant self-service signup), passed via ``GUARDIAN_API_KEY``; without it this
provider is **disabled** and reports a degraded state rather than fabricating data.

License note (§8): we request only ``webTitle`` (headline) and the ``trailText`` standfirst, which
the Open Platform terms permit surfacing. We never fetch or store the full article body, so no
licensed full text leaves or enters the pipeline. ``webPublicationDate`` is the publication time
(UTC) and is used for both ``published_at`` and ``first_seen_at`` (documented approximation, same as
the GDELT provider).

Opt-in / offline-safe: like the GDELT provider this only touches the network when ``enabled`` and a
key are present, so Demo Mode and unit tests stay offline (§17 — no internet in tests). The HTML
tag/entity stripping, pagination, and retry math are pure functions covered by offline unit tests.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .backfill import ProviderUnavailable
from .base import sha256_hex

_GUARDIAN_SEARCH = "https://content.guardianapis.com/search"
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# Guardian caps page-size at 200; keep our default there to minimise request count over a backfill.
_MAX_PAGE_SIZE = 200


def strip_html(text: str) -> str:
    """Guardian ``trailText`` may carry inline markup (<strong>, <a>…) — return clean plain text.

    Removes tags, unescapes HTML entities, collapses whitespace. Pure; no fabrication (only the
    Guardian-supplied snippet is transformed).
    """
    if not text:
        return ""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


class GuardianNewsProvider:
    """Guardian Content API news provider (§7). Disabled without a key (degraded, not faked)."""

    name = "guardian"

    def __init__(
        self,
        query: str,
        *,
        api_key: str | None = None,
        enabled: bool = False,
        from_date: str | None = None,  # "YYYY-MM-DD" (inclusive)
        to_date: str | None = None,  # "YYYY-MM-DD" (inclusive)
        page_size: int = _MAX_PAGE_SIZE,
        max_pages: int = 5,
        timeout: float = 30.0,
        retries: int = 6,
        backoff_s: float = 5.0,
    ) -> None:
        self.query = query
        self.api_key = api_key
        self.enabled = enabled
        self.from_date = from_date
        self.to_date = to_date
        self.page_size = max(1, min(page_size, _MAX_PAGE_SIZE))
        self.max_pages = max(1, max_pages)
        self.timeout = timeout
        self.retries = retries
        self.backoff_s = backoff_s

    def _url(self, page: int) -> str:
        params = {
            "q": self.query,
            "page": str(page),
            "page-size": str(self.page_size),
            "order-by": "oldest",  # deterministic, ascending publication order
            "show-fields": "trailText",
            "api-key": self.api_key or "",
        }
        if self.from_date:
            params["from-date"] = self.from_date
        if self.to_date:
            params["to-date"] = self.to_date
        return f"{_GUARDIAN_SEARCH}?{urllib.parse.urlencode(params)}"

    def fetch(self) -> list[dict]:
        if not self.enabled:
            raise ProviderUnavailable(
                "Guardian live fetch disabled by default (opt-in). Set enabled=True to collect "
                "real news; offline uses FixtureNewsProvider."
            )
        if not self.api_key:
            raise ProviderUnavailable(
                "Guardian API key missing. Get a free developer key at "
                "https://open-platform.theguardian.com/access/ and set GUARDIAN_API_KEY; "
                "no key is ever committed. Offline uses FixtureNewsProvider."
            )
        out: list[dict] = []
        page = 1
        while page <= self.max_pages:
            resp = self._fetch_page(page)
            results = resp.get("results", [])
            out.extend(
                self._to_payload(a)
                for a in results
                if a.get("webUrl") and a.get("webTitle")
            )
            total_pages = int(resp.get("pages", page) or page)
            if page >= total_pages or not results:
                break
            page += 1
        return out

    def _fetch_page(self, page: int) -> dict:
        url = self._url(page)
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "ShockFlowAI/1.0 research"}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
                    raw = r.read().decode("utf-8", "replace")
                body = json.loads(raw).get("response", {})
                if body.get("status") != "ok":
                    raise ProviderUnavailable(
                        f"Guardian API returned status={body.get('status')!r} "
                        f"message={body.get('message')!r}"
                    )
                return body
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
                # A 401/403 is a bad/absent key — retrying will not help; fail fast & clearly.
                if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403):
                    raise ProviderUnavailable(
                        f"Guardian API rejected the key (HTTP {e.code}). Check GUARDIAN_API_KEY."
                    ) from e
                last = e
                if attempt < self.retries - 1:
                    wait = self._retry_wait(e, attempt)
                    reason = "HTTP 429 (rate limit)" if _is_429(e) else type(e).__name__
                    print(
                        f"[guardian] {reason}; waiting {wait:.0f}s "
                        f"(attempt {attempt + 1}/{self.retries})",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
        raise ProviderUnavailable(
            f"Guardian fetch failed after {self.retries} attempts: {last}. If this is a 429, the "
            "developer tier is rate-limited (500 calls/day, ~1/sec) — slow down or re-run later."
        )

    def _retry_wait(self, err: Exception, attempt: int) -> float:
        """Backoff seconds: Retry-After on 429, else exponential for 429, linear otherwise."""
        if isinstance(err, urllib.error.HTTPError) and err.code == 429:
            retry_after = err.headers.get("Retry-After") if err.headers else None
            if retry_after and str(retry_after).strip().isdigit():
                return min(120.0, float(retry_after))
            return min(120.0, self.backoff_s * (2**attempt))
        return self.backoff_s * (attempt + 1)

    @staticmethod
    def _to_payload(a: dict) -> dict:
        url = a["webUrl"]
        published = a["webPublicationDate"]  # ISO-8601 UTC, e.g. "2026-01-15T13:04:22Z"
        fields = a.get("fields") or {}
        return {
            "article_id": sha256_hex(url.encode())[:16],
            "title": a["webTitle"],
            "text": strip_html(fields.get("trailText", "")),  # permitted standfirst snippet only
            "source": "theguardian.com",
            "published_at": published,
            "first_seen_at": published,
            "url_hash": sha256_hex(url.encode()),
            "url": url,
        }


def _is_429(err: Exception) -> bool:
    return isinstance(err, urllib.error.HTTPError) and err.code == 429
