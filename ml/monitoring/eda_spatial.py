"""V2 EDA (2) — 공간·OD·세그먼트·요일×시간 (measured). EDA backlog 1·2·3·6.

`eda_nyc.py`가 분포를 봤다면, 이 모듈은 재배치에 직접 쓰는 **구조**를 본다:
  1) H3 zone × hour-of-day 순흐름(net-flow) — 언제·어디서 자전거가 빠지고 쌓이나
  2) OD(origin→destination) corridor top-N + 순불균형 corridor
  3) 세그먼트 교차: member/casual × e-bike/classic 의 소요시간·거리
  6) 요일 × 시간 heatmap

H3는 **역(station) 단위로만** 매핑한다(2,433개 → h3 호출 2,433회, per-row 아님). 나머지는 스트리밍 집계.
재현: `make v2-eda-spatial` → `reports/v2/monitoring/eda_spatial.json`. 전부 measured.
"""

# 한국어 prose report 문자열이 많아 E501(line-length)만 파일 단위 완화(스타일 한정).
# ruff: noqa: E501
from __future__ import annotations

import json
import zipfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from config.features import H3_RESOLUTION
from ml.monitoring.eda_nyc import _haversine_km
from ml.monitoring.operational_kpis import _csv_members
from pipelines.features.zones import zone_for

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
OUT = Path("reports/v2/monitoring/eda_spatial.json")
OD_CAP = 3_000_000  # OD Counter 상한(초과 시 상위만 유지 → 메모리 bound)


def run(data_dir: Path, chunk: int = 300_000) -> dict:
    zips = sorted(data_dir.glob("*.zip"))
    if not zips:
        return {"status": "blocked_data", "note": f"no trip zips in {data_dir}"}
    total = 0
    dep_h: dict[tuple, int] = {}  # (station, hour) departures
    arr_h: dict[tuple, int] = {}  # (station, hour) arrivals
    st_ll: dict[str, tuple] = {}  # station -> (lat,lng) first-seen
    od: Counter = Counter()  # (start_station, end_station) -> count
    dh_counts: dict[tuple, int] = {}  # (date, hour) -> count  (요일×시간용)
    # segment: (member_casual, rideable) -> [n, dur_sum, dist_sum, dur_n, dist_n]
    seg: dict[tuple, list] = {}

    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for m in _csv_members(zf):
                with zf.open(m) as fh:
                    for ch in pd.read_csv(
                        fh,
                        usecols=lambda c: c in USECOLS,
                        chunksize=chunk,
                        dtype=str,
                        on_bad_lines="skip",
                    ):
                        total += len(ch)
                        sa = ch["started_at"].astype(str)
                        hi = (
                            pd.to_numeric(sa.str.slice(11, 13), errors="coerce")
                            .fillna(-1)
                            .astype(int)
                        )
                        ss = ch["start_station_id"].astype(str)
                        es = ch["end_station_id"].astype(str)
                        for (sid, h), c in ss.groupby([ss, hi]).size().items():
                            dep_h[(sid, h)] = dep_h.get((sid, h), 0) + int(c)
                        for (sid, h), c in es.groupby([es, hi]).size().items():
                            arr_h[(sid, h)] = arr_h.get((sid, h), 0) + int(c)
                        # station first-seen coords
                        for sid, la, lo in zip(ss, ch["start_lat"], ch["start_lng"], strict=False):
                            if sid not in st_ll:
                                try:
                                    st_ll[sid] = (float(la), float(lo))
                                except (TypeError, ValueError):
                                    pass
                        # OD (bounded)
                        od.update(zip(ss, es, strict=False))
                        if len(od) > OD_CAP:
                            od = Counter(dict(od.most_common(500_000)))
                        # date x hour
                        dstr = sa.str.slice(0, 10)
                        for (d, h), c in dstr.groupby([dstr, hi]).size().items():
                            dh_counts[(d, h)] = dh_counts.get((d, h), 0) + int(c)
                        # segments
                        mc = ch["member_casual"].astype(str)
                        rt = ch["rideable_type"].astype(str)
                        st = pd.to_datetime(sa, errors="coerce")
                        en = pd.to_datetime(ch["ended_at"].astype(str), errors="coerce")
                        dur = (en - st).dt.total_seconds() / 60.0
                        km = _haversine_km(
                            pd.to_numeric(ch["start_lat"], errors="coerce"),
                            pd.to_numeric(ch["start_lng"], errors="coerce"),
                            pd.to_numeric(ch["end_lat"], errors="coerce"),
                            pd.to_numeric(ch["end_lng"], errors="coerce"),
                        )
                        for seg_key in [
                            ("member", "electric_bike"),
                            ("member", "classic_bike"),
                            ("casual", "electric_bike"),
                            ("casual", "classic_bike"),
                        ]:
                            mask = (mc == seg_key[0]) & (rt == seg_key[1])
                            if not mask.any():
                                continue
                            d_ok = dur[mask & (dur > 0) & (dur <= 300)]
                            k_ok = km[mask.to_numpy() & np.isfinite(km) & (km >= 0) & (km <= 50)]
                            s = seg.setdefault(seg_key, [0, 0.0, 0.0, 0, 0])
                            s[0] += int(mask.sum())
                            s[1] += float(d_ok.sum())
                            s[3] += int(d_ok.size)
                            s[2] += float(k_ok.sum())
                            s[4] += int(k_ok.size)

    # ---- (1) H3 zone x hour net-flow: 역 흐름을 h3로 집계 ----
    def _safe_zone(la: float, lo: float) -> str | None:
        # 좌표가 유한하고 유효 범위일 때만 H3 매핑(불량 좌표: NaN·0,0·범위밖 스킵)
        if not (np.isfinite(la) and np.isfinite(lo) and -90 <= la <= 90 and -180 <= lo <= 180):
            return None
        if la == 0.0 and lo == 0.0:
            return None
        try:
            return zone_for(la, lo, H3_RESOLUTION)
        except Exception:  # noqa: BLE001 — 불량 좌표는 스킵(집계에서 제외)
            return None

    st_h3 = {sid: z for sid, (la, lo) in st_ll.items() if (z := _safe_zone(la, lo))}
    zdep: dict[tuple, int] = {}
    zarr: dict[tuple, int] = {}
    for (sid, h), c in dep_h.items():
        z3 = st_h3.get(sid)
        if z3 and h >= 0:
            zdep[(z3, h)] = zdep.get((z3, h), 0) + c
    for (sid, h), c in arr_h.items():
        z3 = st_h3.get(sid)
        if z3 and h >= 0:
            zarr[(z3, h)] = zarr.get((z3, h), 0) + c
    cells = {*zdep, *zarr}
    znet = [
        {
            "h3": z3,
            "hour": h,
            "net_in": zarr.get((z3, h), 0) - zdep.get((z3, h), 0),
            "flow": zarr.get((z3, h), 0) + zdep.get((z3, h), 0),
        }
        for (z3, h) in cells
    ]
    znet_sorted = sorted(znet, key=lambda r: -abs(r["net_in"]))
    n_h3 = len({z for (z, _) in cells})

    # ---- (2) OD corridors ----
    top_od = [{"o": o, "d": d, "n": n} for (o, d), n in od.most_common(10)]
    # 순불균형 corridor: flow(a->b) - flow(b->a)
    net_dir = {}
    for (o, d), n in od.items():
        if o == d:
            continue
        key = (o, d) if o < d else (d, o)
        net_dir[key] = net_dir.get(key, 0) + (n if o < d else -n)
    imb_corr = sorted(net_dir.items(), key=lambda kv: -abs(kv[1]))[:8]
    top_imbalanced_corridors = [{"a": k[0], "b": k[1], "net_a_to_b": v} for k, v in imb_corr]

    # ---- (6) 요일 x 시간 heatmap ----
    wh = [[0] * 24 for _ in range(7)]
    for (d, h), c in dh_counts.items():
        try:
            w = date.fromisoformat(d).weekday()
        except ValueError:
            continue
        if 0 <= h < 24:
            wh[w][h] += c

    # ---- (3) 세그먼트 교차 ----
    seg_out = {}
    for k, s in seg.items():
        seg_out[f"{k[0]}|{k[1]}"] = {
            "n": s[0],
            "share": round(s[0] / total, 4) if total else 0,
            "duration_min_mean": round(s[1] / s[3], 2) if s[3] else None,
            "distance_km_mean": round(s[2] / s[4], 3) if s[4] else None,
        }

    return {
        "n_trips": total,
        "h3_resolution": H3_RESOLUTION,
        "n_h3_zones": n_h3,
        "h3_hourly_netflow_top": znet_sorted[:12],
        "od_top_corridors": top_od,
        "od_top_imbalanced_corridors": top_imbalanced_corridors,
        "weekday_hour_heatmap_Mon_first": wh,
        "segments_member_casual_x_bike": seg_out,
        "claim_status": "measured",
        "note": "H3는 station 단위로만 매핑(per-row 아님). OD Counter는 상한 pruning으로 메모리 bound.",
    }


def main() -> int:
    stamp = datetime.now(UTC)
    data_dir = Path("data/raw/nyc")
    if not list(data_dir.glob("*.zip")):
        data_dir = Path("data/raw/citibike")
    eda = run(data_dir)
    report = {
        "run_id": f"run_v2_edaspatial_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/monitoring/eda_spatial.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "trip_source": str(data_dir),
        "eda_spatial": eda,
        "note": "EDA backlog 1·2·3·6 — 공간(H3 시간대별 순흐름)·OD corridor·세그먼트·요일×시간. 전부 measured.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if "n_trips" in eda:
        print(
            f"EDA-spatial {data_dir}: {eda['n_trips']:,} trips · {eda['n_h3_zones']} H3 zones (res {eda['h3_resolution']})"
        )
        print(
            "  H3 hourly net-flow top3:",
            [(r["h3"][:8], f"h{r['hour']}", r["net_in"]) for r in eda["h3_hourly_netflow_top"][:3]],
        )
        print("  OD top corridor:", eda["od_top_corridors"][0] if eda["od_top_corridors"] else None)
        print(
            "  segments:",
            {
                k: (v["share"], v["duration_min_mean"])
                for k, v in eda["segments_member_casual_x_bike"].items()
            },
        )
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
