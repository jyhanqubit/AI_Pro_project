"""V2 운영 KPI(measured only) — 계산 로직 검증(자체 완결: committed fixture + tmp zip)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ml.monitoring.operational_kpis import taxonomy, utilization_kpis

FIX = Path("data/fixtures")


def test_utilization_on_sample_zip(tmp_path):
    # 커밋된 sample CSV를 zip으로 감싸 self-contained 하게 테스트
    csv = (FIX / "citibike_sample.csv").read_text(encoding="utf-8")
    z = tmp_path / "sample.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("sample-citibike-tripdata.csv", csv)
    r = utilization_kpis(tmp_path)
    assert r["n_trips"] >= 1
    assert r["claim_status"] == "measured"
    ratio_keys = ("one_way_ratio", "net_flow_imbalance_index", "member_ratio",
                  "ebike_ratio", "peak_hour_share")
    for k in ratio_keys:
        assert 0.0 <= r[k] <= 1.0
    assert 0 <= r["peak_hour_of_day"] <= 23


def test_utilization_blocked_when_no_zips(tmp_path):
    r = utilization_kpis(tmp_path)
    assert r["status"] == "blocked_data"  # 데이터 없으면 정직하게 blocked


def test_taxonomy_is_measured_only():
    # demo/simulated 지표(재고·service level)는 제외되어 있어야 한다
    labels = " ".join(t["kpi"] for t in taxonomy())
    assert "사용율" in labels
    assert "재고" not in labels and "service level" not in labels
