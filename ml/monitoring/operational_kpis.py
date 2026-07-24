"""V2 운영 KPI — trip history에서 **measured**로만 계산.

예측 metric(WAPE/MASE)만으로 못 보는 '자산이 얼마나 쓰이나(사용율)'를 실제 trip 데이터로 잰다.
이 모듈은 **measured 지표만** 낸다 — 가정(cost/elasticity)이나 실시간 스냅샷에 의존하는 값은 넣지 않는다.

입력 컬럼(Citi Bike trip CSV, 13개 중 사용): started_at · start_station_id · end_station_id ·
member_casual · rideable_type. trip이 실제로 일어났다는 사실만 세므로 모든 값이 measured.

재현: `make v2-kpi` → reports/v2/monitoring/operational_kpis.json
"""

# 한국어 prose report 문자열이 많아 E501(line-length)만 파일 단위 완화(스타일 한정).
# ruff: noqa: E501
from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

USECOLS = ["started_at", "start_station_id", "end_station_id", "member_casual", "rideable_type"]
OUT = Path("reports/v2/monitoring/operational_kpis.json")


def _csv_members(zf: zipfile.ZipFile) -> list[str]:
    """실제 trip CSV 멤버만(맥OS 사이드카/숨김 제외). NYC 월별 zip은 여러 split CSV를 담는다."""
    return [
        n
        for n in zf.namelist()
        if n.lower().endswith(".csv") and "__MACOSX" not in n and not Path(n).name.startswith(".")
    ]


def utilization_kpis(data_dir: Path, chunk: int = 400_000) -> dict:
    """Trip history를 스트리밍해 사용율(자산 회전)·이용 패턴 KPI를 measured로 계산."""
    zips = sorted(data_dir.glob("*.zip"))
    if not zips:
        return {"status": "blocked_data", "note": f"no trip zips in {data_dir}"}
    total = one_way = member = ebike = 0
    hour_counts = [0] * 24
    days: set[str] = set()
    dep: dict[str, int] = {}
    arr: dict[str, int] = {}

    def consume(ch: pd.DataFrame) -> None:
        nonlocal total, one_way, member, ebike
        sa = ch["started_at"].astype(str)
        total += len(ch)
        for h, c in sa.str.slice(11, 13).value_counts().items():
            if str(h).isdigit():
                hour_counts[int(h)] += int(c)
        days.update(sa.str.slice(0, 10).unique().tolist())
        ss, es = ch["start_station_id"].astype(str), ch["end_station_id"].astype(str)
        one_way += int((ss != es).sum())
        member += int((ch["member_casual"].astype(str) == "member").sum())
        ebike += int((ch["rideable_type"].astype(str) == "electric_bike").sum())
        for sid, c in ss.value_counts().items():
            dep[sid] = dep.get(sid, 0) + int(c)
        for sid, c in es.value_counts().items():
            arr[sid] = arr.get(sid, 0) + int(c)

    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for m in _csv_members(zf):
                with zf.open(m) as fh:  # stream member; chunks processed inline (no accumulation)
                    for ch in pd.read_csv(
                        fh, usecols=lambda c: c in USECOLS, chunksize=chunk,
                        dtype=str, on_bad_lines="skip",
                    ):
                        consume(ch)

    n_days = max(len(days), 1)
    n_stations = len({*dep, *arr})
    peak = max(hour_counts)
    peak_hour = hour_counts.index(peak)
    # 구조적 rebalancing 압력: 역별 |도착−출발|/(도착+출발)의 이용량 가중 평균 (전 기간 합산)
    num = den = 0.0
    for sid in {*dep, *arr}:
        a, dd = arr.get(sid, 0), dep.get(sid, 0)
        num += abs(a - dd)
        den += a + dd
    return {
        "source_zips": [z.name for z in zips],
        "n_trips": total,
        "n_days": n_days,
        "n_active_stations": n_stations,
        "daily_trips": round(total / n_days, 1),
        "utilization_trips_per_station_per_day": round(total / n_stations / n_days, 3) if n_stations else 0,
        "one_way_ratio": round(one_way / total, 4) if total else 0,
        "net_flow_imbalance_index": round(num / den, 4) if den else 0.0,
        "peak_hour_of_day": peak_hour,
        "peak_hour_share": round(peak / total, 4) if total else 0,
        "member_ratio": round(member / total, 4) if total else 0,
        "ebike_ratio": round(ebike / total, 4) if total else 0,
        "claim_status": "measured",
        "note": "trip 발생 사실만 집계 — 가정 없음. net_flow_imbalance는 전 기간 합산(장기 균형; 단기 쏠림은 hour 단위 필요).",
    }


def taxonomy() -> list[dict]:
    """제안 KPI 분류 — 정의·공식·계산법·사업 의미. **measured만** 포함."""
    return [
        {"kpi": "사용율 (turnover)", "formula": "trips / active_station / day",
         "how": "총 trip / 활성 station 수 / 일수", "business": "자산 효율 — 자전거당 매출. 낮으면 idle."},
        {"kpi": "daily trips", "formula": "trips / day",
         "how": "총 trip / distinct 날짜 수", "business": "수요 규모."},
        {"kpi": "one-way 비율", "formula": "P(start_station ≠ end_station)",
         "how": "대여≠반납 건수 / 총 trip", "business": "편도 이용 → 구조적 재고 쏠림의 원인."},
        {"kpi": "net-flow 불균형 지수", "formula": "Σ|arr−dep| / Σ(arr+dep)",
         "how": "station별 도착·출발 카운트로 합산", "business": "rebalancing 수요의 크기."},
        {"kpi": "peak-hour share", "formula": "peak-hour trips / total",
         "how": "started_at의 시(hour) 히스토그램 최댓값 / 총 trip", "business": "첨두 부하 — 재배치·요금 타이밍."},
        {"kpi": "member 비율", "formula": "P(member_casual == member)",
         "how": "member 건수 / 총 trip", "business": "구독 이용 비중(안정 매출)."},
        {"kpi": "e-bike 비율", "formula": "P(rideable_type == electric_bike)",
         "how": "electric_bike 건수 / 총 trip", "business": "전기자전거 수요(요금·충전·재배치 영향)."},
    ]


def main() -> int:
    stamp = datetime.now(UTC)
    data_dir = Path("data/raw/nyc")
    if not list(data_dir.glob("*.zip")):
        data_dir = Path("data/raw/citibike")  # fallback: whatever trips are present
    util = utilization_kpis(data_dir)

    report = {
        "run_id": f"run_v2_kpi_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/monitoring/operational_kpis.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "trip_source": str(data_dir),
        "input_columns_used": USECOLS,
        "proposed_kpi_taxonomy_measured_only": taxonomy(),
        "utilization": util,
        "note": "trip history에서 measured로만 계산한 운영 KPI. demo(GBFS)·simulated(ledger) 지표는 제외.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("V2 운영 KPI (measured only)\n" + "=" * 27)
    if "n_trips" in util:
        print(f"source: {data_dir} | {util['n_trips']:,} trips / {util['n_days']}일 / {util['n_active_stations']} stations")
        print(f"  사용율={util['utilization_trips_per_station_per_day']}/station/day · daily={util['daily_trips']:,}")
        print(f"  one_way={util['one_way_ratio']} · imbalance={util['net_flow_imbalance_index']} "
              f"· peak(h{util['peak_hour_of_day']})={util['peak_hour_share']}")
        print(f"  member={util['member_ratio']} · ebike={util['ebike_ratio']}")
    else:
        print(f"utilization: {util.get('status')} ({util.get('note')})")
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
