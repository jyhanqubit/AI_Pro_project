"""V2 EDA — NYC trip 실데이터 1-pass 탐색 분석 (measured, 가정 없음).

다운로드한 NYC trip zip(data/raw/nyc)을 한 번 스트리밍하며 시간/공간/이용자/자산/trip-특성 축의
분포를 집계하고 `reports/v2/monitoring/eda_nyc.json`에 저장한다. 인사이트 정리는
`docs/v2/V2_EDA_INSIGHTS.md`. 재현: `make v2-eda`.

계산하는 것(전부 trip 발생 사실 → measured):
  · 시간: hour-of-day, day-of-week, month 분포 / 첨두
  · 공간: 상위 station, station별 net-flow, hour 단위 불균형 지수(단기 쏠림)
  · trip: 소요시간 분포, 편도 비율, 직선거리 분포
  · 이용자/자산: member vs casual, e-bike vs classic (+ casual 주말 비중)
"""

# 한국어 prose report 문자열이 많아 E501(line-length)만 파일 단위 완화(스타일 한정).
# ruff: noqa: E501
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ml.monitoring.operational_kpis import _csv_members

USECOLS = [
    "started_at",
    "ended_at",
    "start_station_id",
    "end_station_id",
    "member_casual",
    "rideable_type",
    "start_lat",
    "start_lng",
    "end_lat",
    "end_lng",
]
OUT = Path("reports/v2/monitoring/eda_nyc.json")
DUR_BUCKETS = [(0, 5), (5, 10), (10, 20), (20, 45), (45, 1e9)]
DIST_BUCKETS = [(0, 0.5), (0.5, 1), (1, 2), (2, 5), (5, 1e9)]  # km


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def run(data_dir: Path, chunk: int = 300_000) -> dict:
    zips = sorted(data_dir.glob("*.zip"))
    if not zips:
        return {"status": "blocked_data", "note": f"no trip zips in {data_dir}"}
    total = one_way = member = casual_weekend = casual = ebike = 0
    hour = [0] * 24
    date_counts: dict[str, int] = {}
    dep: dict[str, int] = {}
    arr: dict[str, int] = {}
    dep_h: dict[tuple, int] = {}
    arr_h: dict[tuple, int] = {}
    dur_b = [0] * len(DUR_BUCKETS)
    dur_sum = dur_n = 0.0
    dist_b = [0] * len(DIST_BUCKETS)
    dist_sum = dist_n = 0.0

    def wk(dstr: str) -> int:
        try:
            return date.fromisoformat(dstr).weekday()
        except ValueError:
            return -1

    for z in zips:
        with __import__("zipfile").ZipFile(z) as zf:
            for m in _csv_members(zf):
                with zf.open(m) as fh:
                    for ch in pd.read_csv(
                        fh,
                        usecols=lambda c: c in USECOLS,
                        chunksize=chunk,
                        dtype=str,
                        on_bad_lines="skip",
                    ):
                        n = len(ch)
                        total += n
                        sa = ch["started_at"].astype(str)
                        hh = sa.str.slice(11, 13)
                        for h, c in hh.value_counts().items():
                            if str(h).isdigit():
                                hour[int(h)] += int(c)
                        for d, c in sa.str.slice(0, 10).value_counts().items():
                            date_counts[d] = date_counts.get(d, 0) + int(c)
                        ss, es = (
                            ch["start_station_id"].astype(str),
                            ch["end_station_id"].astype(str),
                        )
                        one_way += int((ss != es).sum())
                        member += int((ch["member_casual"].astype(str) == "member").sum())
                        cas = ch["member_casual"].astype(str) == "casual"
                        casual += int(cas.sum())
                        wknd = pd.to_datetime(sa.str.slice(0, 10), errors="coerce").dt.weekday >= 5
                        casual_weekend += int((cas & wknd).sum())
                        ebike += int((ch["rideable_type"].astype(str) == "electric_bike").sum())
                        for sid, c in ss.value_counts().items():
                            dep[sid] = dep.get(sid, 0) + int(c)
                        for sid, c in es.value_counts().items():
                            arr[sid] = arr.get(sid, 0) + int(c)
                        # station × hour-of-day (단기 불균형용)
                        hi = pd.to_numeric(hh, errors="coerce").fillna(-1).astype(int)
                        for (sid, h), c in ss.groupby([ss, hi]).size().items():
                            dep_h[(sid, h)] = dep_h.get((sid, h), 0) + int(c)
                        for (sid, h), c in es.groupby([es, hi]).size().items():
                            arr_h[(sid, h)] = arr_h.get((sid, h), 0) + int(c)
                        # duration (min)
                        st = pd.to_datetime(sa, errors="coerce")
                        en = pd.to_datetime(ch["ended_at"].astype(str), errors="coerce")
                        dur = (en - st).dt.total_seconds() / 60.0
                        dur = dur[(dur > 0) & (dur <= 300)]
                        dur_sum += float(dur.sum())
                        dur_n += int(dur.size)
                        for i, (lo, hej) in enumerate(DUR_BUCKETS):
                            dur_b[i] += int(((dur >= lo) & (dur < hej)).sum())
                        # distance (km, 직선)
                        km = _haversine_km(
                            pd.to_numeric(ch["start_lat"], errors="coerce"),
                            pd.to_numeric(ch["start_lng"], errors="coerce"),
                            pd.to_numeric(ch["end_lat"], errors="coerce"),
                            pd.to_numeric(ch["end_lng"], errors="coerce"),
                        )
                        km = km[np.isfinite(km) & (km >= 0) & (km <= 50)]
                        dist_sum += float(km.sum())
                        dist_n += int(km.size)
                        for i, (lo, hej) in enumerate(DIST_BUCKETS):
                            dist_b[i] += int(((km >= lo) & (km < hej)).sum())

    n_days = max(len(date_counts), 1)
    dow = [0] * 7
    month: dict[str, int] = {}
    for d, c in date_counts.items():
        w = wk(d)
        if w >= 0:
            dow[w] += c
        month[d[:7]] = month.get(d[:7], 0) + c

    # period-aggregate vs hour-grain 불균형
    def imbalance(dd, aa):
        num = den = 0.0
        for k in {*dd, *aa}:
            a, d2 = aa.get(k, 0), dd.get(k, 0)
            num += abs(a - d2)
            den += a + d2
        return round(num / den, 4) if den else 0.0

    top_dep = sorted(dep.items(), key=lambda kv: -kv[1])[:8]
    net = {sid: arr.get(sid, 0) - dep.get(sid, 0) for sid in {*dep, *arr}}
    top_sink = sorted(net.items(), key=lambda kv: -kv[1])[:5]
    top_source = sorted(net.items(), key=lambda kv: kv[1])[:5]

    return {
        "n_trips": total,
        "n_days": n_days,
        "n_stations": len({*dep, *arr}),
        "temporal": {
            "hour_of_day_share": [round(h / total, 4) for h in hour],
            "peak_hours_top3": sorted(range(24), key=lambda h: -hour[h])[:3],
            "day_of_week_share": [round(x / total, 4) for x in dow],  # Mon..Sun
            "weekend_share": round((dow[5] + dow[6]) / total, 4),
            "by_month": {k: month[k] for k in sorted(month)},
        },
        "spatial": {
            "imbalance_index_period": imbalance(dep, arr),
            "imbalance_index_hourly": imbalance(dep_h, arr_h),
            "top_stations_by_departures": [{"id": s, "dep": c} for s, c in top_dep],
            "top_net_sinks": [{"id": s, "net_in": v} for s, v in top_sink],
            "top_net_sources": [{"id": s, "net_in": v} for s, v in top_source],
        },
        "trip": {
            "one_way_ratio": round(one_way / total, 4) if total else 0,
            "duration_min_mean": round(dur_sum / dur_n, 2) if dur_n else None,
            "duration_buckets_min": {
                f"{lo}-{h if h < 1e8 else 'inf'}": dur_b[i] for i, (lo, h) in enumerate(DUR_BUCKETS)
            },
            "distance_km_mean": round(dist_sum / dist_n, 3) if dist_n else None,
            "distance_buckets_km": {
                f"{lo}-{h if h < 1e8 else 'inf'}": dist_b[i]
                for i, (lo, h) in enumerate(DIST_BUCKETS)
            },
        },
        "users_assets": {
            "member_ratio": round(member / total, 4) if total else 0,
            "casual_ratio": round(casual / total, 4) if total else 0,
            "casual_weekend_share_of_casual": round(casual_weekend / casual, 4) if casual else 0,
            "ebike_ratio": round(ebike / total, 4) if total else 0,
        },
        "claim_status": "measured",
    }


def main() -> int:
    stamp = datetime.now(UTC)
    data_dir = Path("data/raw/nyc")
    if not list(data_dir.glob("*.zip")):
        data_dir = Path("data/raw/citibike")
    eda = run(data_dir)
    report = {
        "run_id": f"run_v2_eda_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/monitoring/eda_nyc.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "trip_source": str(data_dir),
        "eda": eda,
        "note": "NYC trip 실데이터 1-pass EDA — 전부 measured(가정 없음).",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if "n_trips" in eda:
        t, sp, tr, ua = eda["temporal"], eda["spatial"], eda["trip"], eda["users_assets"]
        print(
            f"EDA {data_dir}: {eda['n_trips']:,} trips / {eda['n_days']}일 / {eda['n_stations']} stations"
        )
        print(
            f"  peak hours {t['peak_hours_top3']} · weekend_share {t['weekend_share']} · months {list(t['by_month'])}"
        )
        print(
            f"  imbalance period={sp['imbalance_index_period']} vs hourly={sp['imbalance_index_hourly']}"
        )
        print(
            f"  duration_mean={tr['duration_min_mean']}min · distance_mean={tr['distance_km_mean']}km · one_way={tr['one_way_ratio']}"
        )
        print(
            f"  member={ua['member_ratio']} casual={ua['casual_ratio']} (casual weekend {ua['casual_weekend_share_of_casual']}) · ebike={ua['ebike_ratio']}"
        )
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
