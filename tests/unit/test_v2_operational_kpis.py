"""V2 운영 KPI — 계산 로직 검증(자체 완결: committed fixture/artifact + tmp zip)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from ml.monitoring.operational_kpis import (
    inventory_kpis,
    service_level_kpis,
    utilization_kpis,
)

FIX = Path("data/fixtures")


def test_inventory_kpis_rates_in_range():
    r = inventory_kpis(FIX / "gbfs_station_status.json")
    assert r["n_stations"] >= 1
    rate_keys = ("bike_availability_rate", "stockout_rate", "dock_availability_rate",
                 "full_rate", "mean_fill_ratio")
    for k in rate_keys:
        assert 0.0 <= r[k] <= 1.0
    assert r["claim_status"] == "demo_fixture"  # GBFS 스냅샷 = 실시간만


def test_utilization_on_sample_zip(tmp_path):
    # 커밋된 sample CSV를 zip으로 감싸 self-contained 하게 테스트
    csv = (FIX / "citibike_sample.csv").read_text(encoding="utf-8")
    z = tmp_path / "sample.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("sample-citibike-tripdata.csv", csv)
    r = utilization_kpis(tmp_path)
    assert r["n_trips"] >= 1
    assert r["claim_status"] == "measured"
    assert 0.0 <= r["one_way_ratio"] <= 1.0
    assert 0.0 <= r["net_flow_imbalance_index"] <= 1.0


def test_utilization_blocked_when_no_zips(tmp_path):
    r = utilization_kpis(tmp_path)
    assert r["status"] == "blocked_data"  # 데이터 없으면 정직하게 blocked


def test_service_level_from_committed_ledger():
    r = service_level_kpis(Path("reports/v2/ledger/profit_regret.json"))
    pm = r["by_policy"]["promoted_model"]
    # fill_rate + unmet_demand_rate ≈ 1 (충족 + 미충족)
    assert abs(pm["fill_rate"] + pm["unmet_demand_rate"] - 1.0) < 1e-6
    assert r["claim_status"] == "simulated"
