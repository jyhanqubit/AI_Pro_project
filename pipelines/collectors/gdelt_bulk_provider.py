"""Real news provider: GDELT 2.0 GKG bulk file exports (CLAUDE.md §7, §7.4).

GDELT publishes a Global Knowledge Graph (GKG) export file every 15 minutes at
``http://data.gdeltproject.org/gdeltv2/<YYYYMMDDHHMMSS>.gkg.csv.zip``. Reading these files directly
sidesteps the two limits of the DOC 2.0 API used elsewhere:

  * **No rate limit** — these are plain static files, not a throttled query endpoint (no HTTP 429).
  * **Full historical archive** — files exist back to 2015, not just the last few months.

Honest limitation (documented, not worked around): the GKG carries the article **URL, source
domain, publish time, and GDELT-computed themes/locations** — but **not the headline text** (only
the DOC API scrapes titles at query time). So this provider emits real provenance plus GDELT's own
theme/location tags (clearly labelled ``[GDELT GKG]`` in ``text``, never fabricated prose) and
filters on those tags. It is best used as a **coverage / event-signal source**; for headline-driven
LLM prose extraction, prefer the Guardian provider.

Opt-in / offline-safe: only touches the network when ``enabled``. URL construction, GKG row
parsing, and the NYC/theme filter are pure functions covered by offline unit tests (§17).
"""

from __future__ import annotations

import io
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta

from .backfill import ProviderUnavailable
from .base import sha256_hex

_GDELT_BASE = "http://data.gdeltproject.org/gdeltv2"

# GKG 2.1 tab-delimited column indices we use (0-based; see GDELT GKG 2.1 codebook).
_COL_DATE = 1  # V2.1DATE  "YYYYMMDDHHMMSS"
_COL_SOURCE = 3  # V2SourceCommonName (domain)
_COL_URL = 4  # V2DocumentIdentifier (article URL)
_COL_THEMES = 7  # V1Themes  "THEME;THEME;..."
_COL_LOCATIONS = 9  # V1Locations  "type#fullname#cc#adm1#lat#long#featureid;..."

# GDELT theme *substrings* that mark a row as bike-demand relevant (transit disruption, crowds,
# weather shocks, road closures). Configurable; matched case-insensitively against V1Themes.
DEFAULT_THEME_TERMS: tuple[str, ...] = (
    "TRANSPORT",
    "TRANSIT",
    "ROAD",
    "TRAFFIC",
    "PROTEST",
    "STRIKE",
    "DISASTER",
    "FLOOD",
    "STORM",
    "STATE_OF_EMERGENCY",
    "SPORT",
    "ENTERTAINMENT",
    "EVENT",
)


def gkg_file_url(stamp: str) -> str:
    """URL of the 15-minute GKG export for a ``YYYYMMDDHHMMSS`` slice stamp."""
    return f"{_GDELT_BASE}/{stamp}.gkg.csv.zip"


def _parse_stamp(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def iter_slice_stamps(start: str, end: str) -> list[str]:
    """All 15-minute slice stamps in ``[start, end)`` (GDELT publishes at :00/:15/:30/:45 UTC).

    ``start``/``end`` are ``YYYYMMDDHHMMSS``. Snaps ``start`` down to the enclosing quarter-hour.
    """
    a, b = _parse_stamp(start), _parse_stamp(end)
    a = a.replace(minute=(a.minute // 15) * 15, second=0, microsecond=0)
    out: list[str] = []
    cur = a
    step = timedelta(minutes=15)
    while cur < b:
        out.append(cur.strftime("%Y%m%d%H%M%S"))
        cur += step
    return out


def _split_locations(raw: str) -> list[tuple[str, str, str]]:
    """V1Locations -> list of (fullname, country_code, adm1_code). Best-effort; skips malformed."""
    out: list[tuple[str, str, str]] = []
    for loc in raw.split(";"):
        if not loc:
            continue
        parts = loc.split("#")
        if len(parts) >= 4:
            out.append((parts[1], parts[2], parts[3]))
    return out


def _is_nyc(locations: list[tuple[str, str, str]]) -> bool:
    """True if any location is in New York (US-NY ADM1, or a 'New York' place in the US)."""
    for fullname, cc, adm1 in locations:
        if adm1 == "USNY":
            return True
        if cc == "US" and "new york" in fullname.lower():
            return True
    return False


def parse_gkg_row(line: str) -> dict | None:
    """Parse one GKG 2.1 row into {date, source, url, themes[], locations[]}. None if unusable."""
    cols = line.split("\t")
    if len(cols) <= _COL_LOCATIONS:
        return None
    url = cols[_COL_URL].strip()
    date = cols[_COL_DATE].strip()
    if not url or not date:
        return None
    themes = [t for t in cols[_COL_THEMES].split(";") if t]
    locations = _split_locations(cols[_COL_LOCATIONS])
    return {
        "date": date,
        "source": cols[_COL_SOURCE].strip() or "gdelt",
        "url": url,
        "themes": themes,
        "locations": locations,
    }


def row_matches(row: dict, theme_terms: tuple[str, ...], require_nyc: bool = True) -> bool:
    """Keep a row only if it is NYC-located (optional) and hits a relevant theme substring."""
    if require_nyc and not _is_nyc(row["locations"]):
        return False
    blob = ";".join(row["themes"]).upper()
    return any(term.upper() in blob for term in theme_terms)


def _theme_summary(row: dict) -> str:
    """Real, clearly-labelled GDELT tags for ``text`` (NOT fabricated article prose)."""
    themes = sorted({t.split(",")[0] for t in row["themes"]})[:8]
    places = sorted({fn for fn, _cc, _adm in row["locations"]})[:3]
    return f"[GDELT GKG] themes: {', '.join(themes)} | loc: {', '.join(places)}"


def gkg_row_to_payload(row: dict) -> dict:
    """Real provenance + labelled GDELT tags. Empty ``title`` (GKG has no headline; not faked)."""
    url = row["url"]
    when = _parse_stamp(row["date"]).isoformat()
    return {
        "article_id": sha256_hex(url.encode())[:16],
        "title": "",  # GKG carries no headline; leaving empty rather than fabricating one
        "text": _theme_summary(row),
        "source": row["source"],
        "published_at": when,
        "first_seen_at": when,
        "url_hash": sha256_hex(url.encode()),
        "url": url,
    }


class GdeltBulkNewsProvider:
    """GDELT GKG bulk-file news provider (§7). No key, no rate limit; full historical archive."""

    name = "gdelt_bulk"

    def __init__(
        self,
        *,
        enabled: bool = False,
        start: str | None = None,  # "YYYYMMDDHHMMSS" UTC
        end: str | None = None,
        theme_terms: tuple[str, ...] = DEFAULT_THEME_TERMS,
        require_nyc: bool = True,
        max_files: int = 96,  # 96 * 15min = 24h; cap so a run never downloads unbounded history
        timeout: float = 30.0,
        retries: int = 3,
        backoff_s: float = 3.0,
    ) -> None:
        self.enabled = enabled
        self.start = start
        self.end = end
        self.theme_terms = theme_terms
        self.require_nyc = require_nyc
        self.max_files = max(1, max_files)
        self.timeout = timeout
        self.retries = retries
        self.backoff_s = backoff_s

    def fetch(self) -> list[dict]:
        if not self.enabled:
            raise ProviderUnavailable(
                "GDELT bulk fetch disabled by default (opt-in). Set enabled=True to download the "
                "GKG export files; offline uses FixtureNewsProvider."
            )
        if not (self.start and self.end):
            raise ProviderUnavailable(
                "GDELT bulk needs an explicit --start/--end window (YYYYMMDDHHMMSS)."
            )
        stamps = iter_slice_stamps(self.start, self.end)
        if len(stamps) > self.max_files:
            print(
                f"[gdelt_bulk] window has {len(stamps)} 15-min files; capping at max_files="
                f"{self.max_files} (raise --max-files, or narrow the window / fetch day-by-day).",
                file=sys.stderr,
            )
            stamps = stamps[: self.max_files]

        seen_urls: set[str] = set()
        out: list[dict] = []
        for stamp in stamps:
            for row in self._fetch_slice(stamp):
                if not row_matches(row, self.theme_terms, self.require_nyc):
                    continue
                if row["url"] in seen_urls:  # same article across adjacent slices
                    continue
                seen_urls.add(row["url"])
                out.append(gkg_row_to_payload(row))
        return out

    def _fetch_slice(self, stamp: str) -> list[dict]:
        """Download + unzip + parse one 15-min GKG file. Missing file (404) -> empty, not error."""
        url = gkg_file_url(stamp)
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "ShockFlowAI/1.0 research"}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
                    payload = r.read()
                with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                    name = zf.namelist()[0]
                    text = zf.read(name).decode("utf-8", "replace")
                rows = [parse_gkg_row(line) for line in text.splitlines() if line]
                return [row for row in rows if row is not None]
            except urllib.error.HTTPError as e:
                if e.code == 404:  # some 15-min slices simply do not exist; skip quietly
                    return []
                if attempt < self.retries - 1:
                    time.sleep(self.backoff_s * (attempt + 1))
            except (urllib.error.URLError, TimeoutError, zipfile.BadZipFile, OSError):
                if attempt < self.retries - 1:
                    time.sleep(self.backoff_s * (attempt + 1))
        print(f"[gdelt_bulk] slice {stamp} unavailable after {self.retries} tries", file=sys.stderr)
        return []
