"""GET /v2/live/inventory: the Supabase-backed live inventory route.

Offline contract: without SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY the route degrades with a
reason (never a fabricated inventory); with a stubbed PostgREST fetcher it summarises the latest
snapshot and labels it mode=live with the snapshot's own freshness. No test touches the network
(pytest-socket blocks it anyway).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from config.settings import get_settings
from services.api import live_inventory as li
from services.api.app import create_app
from services.api.replay import reset_engine

ROWS = [
    {
        "station_id": "a",
        "name": "Grove St PATH",
        "region_id": "70",
        "lat": 40.7,
        "lng": -74.0,
        "capacity": 30,
        "bikes": 0,
        "docks": 30,
        "fill_ratio": 0.0,
        "is_installed": True,
        "is_renting": True,
        "is_returning": True,
        "fetched_at": "2026-10-02T12:00:00+00:00",
        "source_last_updated": "2026-10-02T11:59:30+00:00",
        "mode": "live",
    },
    {
        "station_id": "b",
        "name": "Hoboken Terminal",
        "region_id": "311",
        "lat": 40.73,
        "lng": -74.03,
        "capacity": 40,
        "bikes": 2,
        "docks": 38,
        "fill_ratio": 0.05,
        "is_installed": True,
        "is_renting": True,
        "is_returning": True,
        "fetched_at": "2026-10-02T12:00:00+00:00",
        "source_last_updated": "2026-10-02T11:59:30+00:00",
        "mode": "live",
    },
    {
        "station_id": "c",
        "name": "W 35 St & 9 Ave",
        "region_id": "71",
        "lat": 40.75,
        "lng": -73.99,
        "capacity": 50,
        "bikes": 50,
        "docks": 0,
        "fill_ratio": 1.0,
        "is_installed": True,
        "is_renting": True,
        "is_returning": True,
        "fetched_at": "2026-10-02T12:00:00+00:00",
        "source_last_updated": "2026-10-02T11:59:30+00:00",
        "mode": "live",
    },
    {
        "station_id": "d",
        "name": "Closed",
        "region_id": "71",
        "lat": 40.76,
        "lng": -73.98,
        "capacity": 20,
        "bikes": 7,
        "docks": 13,
        "fill_ratio": 0.35,
        "is_installed": True,
        "is_renting": False,
        "is_returning": False,
        "fetched_at": "2026-10-02T12:00:00+00:00",
        "source_last_updated": "2026-10-02T11:59:30+00:00",
        "mode": "live",
    },
]


@pytest.fixture
def client() -> TestClient:
    reset_engine()
    return TestClient(create_app())


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch):
    s = get_settings()
    monkeypatch.setattr(s, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(s, "supabase_publishable_key", "sb_publishable_test")
    return s


def test_degrades_when_not_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "supabase_url", None)
    monkeypatch.setattr(s, "supabase_publishable_key", None)
    d = client.get("/v2/live/inventory").json()
    assert d["status"] == "degraded" and d["mode"] == "live"
    assert d["claim_status"] == "blocked_external"
    assert "not configured" in d["degraded_reason"]
    assert d["summary"] is None and d["lowest"] == [] and d["fullest"] == []


def test_degrades_when_supabase_is_unreachable(client: TestClient, configured, monkeypatch) -> None:
    def boom(url: str, key: str, timeout_s: float):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(li, "fetch_rows", boom)
    d = client.get("/v2/live/inventory").json()
    assert d["status"] == "degraded" and "ConnectError" in d["degraded_reason"]


def test_live_summary_and_ranking(client: TestClient, configured, monkeypatch) -> None:
    captured: dict = {}

    def fake(url: str, key: str, timeout_s: float):
        captured.update(url=url, key=key)
        return [dict(r) for r in ROWS]

    monkeypatch.setattr(li, "fetch_rows", fake)
    d = client.get("/v2/live/inventory?limit=2").json()
    assert captured == {"url": "https://example.supabase.co", "key": "sb_publishable_test"}
    assert d["status"] == "live" and d["mode"] == "live" and d["claim_status"] == "measured"
    assert d["source"] == "supabase:live_inventory_latest"
    assert d["fetched_at"] == "2026-10-02T12:00:00+00:00"
    assert d["run_id"] == "gbfs_station_status_20261002T120000Z"
    assert d["age_minutes"] is not None and d["age_minutes"] >= 0

    s = d["summary"]
    assert s == {
        "n_stations": 4,
        "bikes_total": 59,
        "docks_total": 81,
        "empty_renting": 1,  # a (0 bikes, renting); d is closed and must not count
        "low_renting": 2,  # a and b (<= 2 bikes)
        "full_returning": 1,  # c
        "not_renting": 1,  # d
    }
    assert [x["station_id"] for x in d["lowest"]] == ["a", "b"]  # closed station excluded, limit 2
    assert [x["station_id"] for x in d["fullest"]][0] == "c"


def test_region_filter_and_empty_region(client: TestClient, configured, monkeypatch) -> None:
    monkeypatch.setattr(li, "fetch_rows", lambda url, key, timeout_s: [dict(r) for r in ROWS])
    jc = client.get("/v2/live/inventory?region=70").json()
    assert jc["status"] == "live" and jc["summary"]["n_stations"] == 1 and jc["region_id"] == "70"
    none = client.get("/v2/live/inventory?region=999").json()
    assert none["status"] == "degraded" and "region 999" in none["degraded_reason"]


def test_age_is_measured_from_the_snapshot(configured, monkeypatch) -> None:
    out = li.live_inventory(
        fetcher=lambda url, key, timeout_s: [dict(r) for r in ROWS],
        now=datetime(2026, 10, 2, 13, 30, tzinfo=UTC),
    )
    assert out["age_minutes"] == 90.0
