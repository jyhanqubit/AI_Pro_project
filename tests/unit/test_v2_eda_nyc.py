"""V2 EDA(NYC trip) — 1-pass 집계 로직 검증(자체 완결: committed sample → tmp zip)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ml.monitoring.eda_nyc import run

FIX = Path("data/fixtures")


def _sample_dir(tmp_path):
    csv = (FIX / "citibike_sample.csv").read_text(encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "s.zip", "w") as zf:
        zf.writestr("s-citibike-tripdata.csv", csv)
    return tmp_path


def test_eda_structure_and_ranges(tmp_path):
    r = run(_sample_dir(tmp_path))
    assert r["claim_status"] == "measured"
    assert r["n_trips"] >= 1
    for section in ("temporal", "spatial", "trip", "users_assets"):
        assert section in r
    assert 0.0 <= r["trip"]["one_way_ratio"] <= 1.0
    assert 0.0 <= r["spatial"]["imbalance_index_hourly"] <= 1.0
    assert len(r["temporal"]["hour_of_day_share"]) == 24
    assert len(r["temporal"]["day_of_week_share"]) == 7


def test_eda_blocked_when_no_zips(tmp_path):
    assert run(tmp_path)["status"] == "blocked_data"
