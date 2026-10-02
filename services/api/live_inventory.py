"""Live station inventory served from the Supabase project (CLAUDE.md sections 3, 7.3, 12).

The Supabase database collects Citi Bike GBFS inventory on its own schedule (supabase/README.md)
and exposes the latest snapshot as the ``live_inventory_latest`` view. This module reads that view
over PostgREST with the publishable key (row-level security makes it read-only) and shapes it for
the operator cockpit.

Honesty rules: the result is labelled ``mode=live`` with the snapshot's own ``fetched_at`` as its
freshness; when Supabase is not configured or unreachable the route returns ``status=degraded``
with the reason, never a fabricated inventory. Demo Mode does not need any of this.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from config.settings import get_settings

VIEW = "live_inventory_latest"
SOURCE = f"supabase:{VIEW}"
MAX_ROWS = 5000  # the network is ~2,500 stations; a hard cap keeps a bad view from flooding us
PAGE = 1000  # PostgREST max-rows on Supabase; one Range page per request
LOW_BIKES = 2  # "about to run out" threshold for the shortage list

Fetcher = Callable[[str, str, float], list[dict[str, Any]]]


def fetch_rows(
    url: str, key: str, timeout_s: float, *, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Read every row of the latest-snapshot view (PostgREST, publishable key, read-only).

    PostgREST caps one response at the project's ``max-rows`` (1,000 on Supabase by default),
    which is below the ~2,500-station network, so the view is read in pages via the ``Range``
    header until a short page arrives. ``MAX_ROWS`` bounds the total.
    """
    endpoint = f"{url.rstrip('/')}/rest/v1/{VIEW}"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    params = {"select": "*", "order": "station_id.asc"}
    rows: list[dict[str, Any]] = []
    own = client is None
    c = client or httpx.Client(timeout=timeout_s)
    try:
        for start in range(0, MAX_ROWS, PAGE):
            r = c.get(
                endpoint,
                params=params,
                headers={**headers, "Range-Unit": "items", "Range": f"{start}-{start + PAGE - 1}"},
            )
            r.raise_for_status()
            page = r.json()
            if not isinstance(page, list):
                raise ValueError(f"unexpected PostgREST payload: {type(page).__name__}")
            rows.extend(page)
            if len(page) < PAGE:
                break
    finally:
        if own:
            c.close()
    return rows


def _degraded(reason: str, *, limit: int, region: str | None) -> dict[str, Any]:
    return {
        "status": "degraded",
        "mode": "live",
        "claim_status": "blocked_external",
        "source": SOURCE,
        "fetched_at": None,
        "source_last_updated": None,
        "age_minutes": None,
        "limit": limit,
        "region_id": region,
        "summary": None,
        "lowest": [],
        "fullest": [],
        "degraded_reason": reason,
        "note": (
            "지금은 라이브 재고를 불러올 수 없습니다. Supabase 연결이 설정되지 않았거나 "
            "닿지 않습니다. 데모와 과거 재생 화면은 이와 무관하게 동작합니다."
        ),
    }


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _station(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "station_id": row.get("station_id"),
        "name": row.get("name"),
        "region_id": row.get("region_id"),
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "capacity": row.get("capacity"),
        "bikes": int(row.get("bikes") or 0),
        "docks": int(row.get("docks") or 0),
        "fill_ratio": row.get("fill_ratio"),
        "is_renting": bool(row.get("is_renting")),
        "is_returning": bool(row.get("is_returning")),
    }


def live_inventory(
    *,
    limit: int = 10,
    region: str | None = None,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Latest live inventory summary + the stations closest to empty / full."""
    settings = get_settings()
    url, key = settings.supabase_url, settings.supabase_publishable_key
    if not url or not key:
        return _degraded(
            "not configured: set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY",
            limit=limit,
            region=region,
        )
    try:
        rows = (fetcher or fetch_rows)(url, key, settings.supabase_timeout_s)
    except (httpx.HTTPError, ValueError) as exc:
        return _degraded(f"{type(exc).__name__}: {exc}", limit=limit, region=region)

    if region:
        rows = [r for r in rows if str(r.get("region_id")) == str(region)]
    if not rows:
        return _degraded(
            "the latest snapshot has no rows" + (f" for region {region}" if region else ""),
            limit=limit,
            region=region,
        )

    stations = [_station(r) for r in rows]
    fetched = min((t for t in (_ts(r.get("fetched_at")) for r in rows) if t), default=None)
    source_updated = max(
        (t for t in (_ts(r.get("source_last_updated")) for r in rows) if t), default=None
    )
    current = now or datetime.now(UTC)
    age_min = round((current - fetched).total_seconds() / 60, 1) if fetched else None

    renting = [s for s in stations if s["is_renting"]]
    returning = [s for s in stations if s["is_returning"]]
    lowest = sorted(
        renting, key=lambda s: (s["bikes"], s["fill_ratio"] if s["fill_ratio"] is not None else 1.0)
    )
    fullest = sorted(returning, key=lambda s: (s["docks"], -(s["fill_ratio"] or 0.0)))

    summary = {
        "n_stations": len(stations),
        "bikes_total": sum(s["bikes"] for s in stations),
        "docks_total": sum(s["docks"] for s in stations),
        "empty_renting": sum(1 for s in renting if s["bikes"] == 0),
        "low_renting": sum(1 for s in renting if s["bikes"] <= LOW_BIKES),
        "full_returning": sum(1 for s in returning if s["docks"] == 0),
        "not_renting": sum(1 for s in stations if not s["is_renting"]),
    }
    return {
        "status": "live",
        "mode": "live",
        "claim_status": "measured",
        "source": SOURCE,
        "run_id": f"gbfs_station_status_{fetched.strftime('%Y%m%dT%H%M%SZ') if fetched else 'unknown'}",
        "fetched_at": fetched.isoformat() if fetched else None,
        "source_last_updated": source_updated.isoformat() if source_updated else None,
        "age_minutes": age_min,
        "limit": limit,
        "region_id": region,
        "summary": summary,
        "lowest": lowest[: max(1, limit)],
        "fullest": fullest[: max(1, limit)],
        "note": (
            "Supabase에 매일 적재되는 Citi Bike GBFS 재고 스냅숏의 최신분입니다. fetched_at이 스냅숏 "
            "시각이고 age_minutes가 그 이후 경과 시간입니다. 관측값이며 예측이 아닙니다."
        ),
    }
