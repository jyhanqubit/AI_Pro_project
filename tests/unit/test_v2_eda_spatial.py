"""V2 EDA(2) 공간·OD·세그먼트·요일×시간 — 집계 로직 검증(자체 완결)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ml.monitoring.eda_spatial import run

FIX = Path("data/fixtures")


def _sample_dir(tmp_path):
    csv = (FIX / "citibike_sample.csv").read_text(encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "s.zip", "w") as zf:
        zf.writestr("s-citibike-tripdata.csv", csv)
    return tmp_path


def test_spatial_structure(tmp_path):
    r = run(_sample_dir(tmp_path))
    assert r["claim_status"] == "measured"
    assert r["n_h3_zones"] >= 1
    for key in ("h3_hourly_netflow_top", "od_top_corridors",
                "od_top_imbalanced_corridors", "segments_member_casual_x_bike"):
        assert key in r
    wh = r["weekday_hour_heatmap_Mon_first"]
    assert len(wh) == 7 and all(len(row) == 24 for row in wh)
    # net-flow 항목은 h3 id + hour + net_in 구조
    if r["h3_hourly_netflow_top"]:
        top = r["h3_hourly_netflow_top"][0]
        assert {"h3", "hour", "net_in", "flow"} <= set(top)


def test_spatial_blocked_when_no_zips(tmp_path):
    assert run(tmp_path)["status"] == "blocked_data"
