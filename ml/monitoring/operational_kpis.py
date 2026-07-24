"""V2 운영 KPI — 예측 정확도 밖의 '사업/운영' 지표를 실데이터로 계산.

배경: WAPE/MASE 같은 예측 metric만으로는 '자산이 얼마나 잘 쓰이나(사용율)', '탈 자전거가 있나
(재고율)'를 못 본다. 이 모듈은 그 운영 KPI를 실제 데이터에서 계산하되, source에 따라 정직하게 라벨한다.

KPI를 source별로 나눈다(핵심 규율):
  · 사용율(utilization) — trip history에서 measured (자산 효율의 직접 지표)
  · 재고(inventory) 가용/품절 — GBFS station_status에서. 실시간 스냅샷만 존재(과거치 없음) →
    fixture는 demo_fixture, 과거 시계열은 blocked_data
  · service level(충족률) — profit/regret ledger에서 simulated (shortage/overflow 기반)

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


def _csv_members(zf: zipfile.ZipFile) -> list[str]:
    """실제 trip CSV 멤버만(맥OS 사이드카/숨김 제외). NYC 월별 zip은 여러 split CSV를 담는다."""
    return [
        n
        for n in zf.namelist()
        if n.lower().endswith(".csv") and "__MACOSX" not in n and not Path(n).name.startswith(".")
    ]


NY_DOCK_COLS = ["started_at", "start_station_id", "end_station_id"]
OUT = Path("reports/v2/monitoring/operational_kpis.json")


# ---------------------------------------------------------------- inventory (GBFS)
def inventory_kpis(status_path: Path) -> dict:
    """GBFS station_status 스냅샷에서 재고 가용/품절 KPI. capacity = bikes+docks proxy."""
    d = json.loads(status_path.read_text(encoding="utf-8"))
    st = d.get("data", {}).get("stations") or d.get("stations") or []
    installed = [s for s in st if s.get("is_installed", 1)]
    n = len(installed)
    if not n:
        return {"n_stations": 0, "status": "blocked_data", "note": "no stations in snapshot"}

    def frac(pred):
        return round(sum(1 for s in installed if pred(s)) / n, 4)

    bikes = lambda s: s.get("num_bikes_available", 0)  # noqa: E731
    docks = lambda s: s.get("num_docks_available", 0)  # noqa: E731
    fill = [bikes(s) / max(bikes(s) + docks(s), 1) for s in installed]
    return {
        "n_stations": n,
        "bike_availability_rate": frac(lambda s: s.get("is_renting", 1) and bikes(s) >= 1),
        "stockout_rate": frac(lambda s: bikes(s) == 0),
        "dock_availability_rate": frac(lambda s: s.get("is_returning", 1) and docks(s) >= 1),
        "full_rate": frac(lambda s: docks(s) == 0),
        "mean_fill_ratio": round(sum(fill) / n, 4),
        "claim_status": "demo_fixture",
        "note": (
            "GBFS는 실시간 스냅샷만 제공 → fixture는 demo. 과거 시계열 재고율은 라이브 폴링 축적 "
            "필요(blocked_data). 라이브 모드에서 이 함수가 그대로 measured가 된다."
        ),
    }


# ---------------------------------------------------------------- utilization (trips)
def utilization_kpis(data_dir: Path, chunk: int = 400_000) -> dict:
    """Trip history를 스트리밍해 사용율(자산 회전) KPI를 measured로 계산."""
    zips = sorted(data_dir.glob("*.zip"))
    if not zips:
        return {"status": "blocked_data", "note": f"no trip zips in {data_dir}"}
    total = one_way = 0
    hour_counts = [0] * 24
    days: set[str] = set()
    dep: dict[str, int] = {}
    arr: dict[str, int] = {}

    def consume(ch: pd.DataFrame) -> None:
        nonlocal total, one_way
        sa = ch["started_at"].astype(str)
        total += len(ch)
        for h, c in sa.str.slice(11, 13).value_counts().items():
            if str(h).isdigit():
                hour_counts[int(h)] += int(c)
        days.update(sa.str.slice(0, 10).unique().tolist())
        ss, es = ch["start_station_id"].astype(str), ch["end_station_id"].astype(str)
        one_way += int((ss != es).sum())
        for sid, c in ss.value_counts().items():
            dep[sid] = dep.get(sid, 0) + int(c)
        for sid, c in es.value_counts().items():
            arr[sid] = arr.get(sid, 0) + int(c)

    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for m in _csv_members(zf):
                with zf.open(m) as fh:  # stream member; chunks processed inline (no accumulation)
                    for ch in pd.read_csv(
                        fh,
                        usecols=lambda c: c in NY_DOCK_COLS,
                        chunksize=chunk,
                        dtype=str,
                        on_bad_lines="skip",
                    ):
                        consume(ch)
    n_days = max(len(days), 1)
    n_stations = len({*dep, *arr})
    peak = max(hour_counts)
    mean_h = total / 24 if total else 1
    # 구조적 rebalancing 압력: 역별 |도착−출발|/(도착+출발)의 이용량 가중 평균
    num = den = 0.0
    for sid in {*dep, *arr}:
        a, dd = arr.get(sid, 0), dep.get(sid, 0)
        if a + dd:
            num += abs(a - dd)
            den += a + dd
    imbalance = round(num / den, 4) if den else 0.0
    return {
        "n_trips": total,
        "n_days": n_days,
        "n_active_stations": n_stations,
        "daily_trips": round(total / n_days, 1),
        "trips_per_active_station_per_day": round(total / n_stations / n_days, 3)
        if n_stations
        else 0,
        "peak_hour_share": round(peak / total, 4) if total else 0,
        "peak_to_mean_ratio": round(peak / mean_h, 2) if total else 0,
        "one_way_ratio": round(one_way / total, 4) if total else 0,
        "net_flow_imbalance_index": imbalance,
        "claim_status": "measured",
        "note": "trip history에서 직접 계산 — 자산 회전(사용율)과 구조적 rebalancing 압력의 measured 지표.",
    }


# ---------------------------------------------------------------- service level (ledger)
def service_level_kpis(ledger_path: Path) -> dict:
    """profit/regret ledger에서 수요 충족률(service level). simulated 단위 기반."""
    if not ledger_path.exists():
        return {"status": "blocked_data", "note": "no ledger artifact"}
    d = json.loads(ledger_path.read_text(encoding="utf-8"))
    bp = d.get("by_policy", {})
    out = {}
    for pol in ("no_action", "promoted_model", "oracle"):
        v = bp.get(pol)
        if not v:
            continue
        r, sh, ov = (
            v.get("realized_rentals", 0),
            v.get("shortage_units", 0),
            v.get("overflow_units", 0),
        )
        demand = r + sh
        out[pol] = {
            "fill_rate": round(r / demand, 4) if demand else None,  # 충족된 수요 비율
            "unmet_demand_rate": round(sh / demand, 4) if demand else None,  # 품절로 놓친 비율
            "overflow_units": ov,
        }
    return {
        "by_policy": out,
        "claim_status": "simulated",
        "note": "ledger 단위(측정) + 금액 가정(simulated). fill_rate=충족 수요/총수요.",
    }


def taxonomy() -> list[dict]:
    """추가 KPI 제안 — 정의 · 공식 · source · claim_status · 사업 의미."""
    return [
        {
            "kpi": "사용율 (utilization / turnover)",
            "formula": "trips / active_station / day",
            "source": "trip history",
            "claim_status": "measured",
            "business": "자산 효율 — 자전거당 매출. 낮으면 idle 자산(놀고 있음).",
        },
        {
            "kpi": "재고 가용률 (bike availability)",
            "formula": "P(bikes ≥ 1 & renting)",
            "source": "GBFS station_status",
            "claim_status": "demo_fixture / live→measured",
            "business": "빌릴 수 있는가 — 낮으면 trip·매출 손실.",
        },
        {
            "kpi": "품절률 (stockout rate)",
            "formula": "P(bikes == 0)",
            "source": "GBFS station_status",
            "claim_status": "demo_fixture / live→measured",
            "business": "rebalancing 우선순위 신호(부족). ledger shortage와 직결.",
        },
        {
            "kpi": "반납 가용률 / 포화률 (dock avail / full)",
            "formula": "P(docks ≥ 1) / P(docks == 0)",
            "source": "GBFS station_status",
            "claim_status": "demo_fixture / live→measured",
            "business": "반납 가능한가 — 포화 시 rider 이탈, overflow 비용.",
        },
        {
            "kpi": "net-flow 불균형 지수",
            "formula": "Σ|arr−dep| / Σ(arr+dep)",
            "source": "trip history",
            "claim_status": "measured",
            "business": "구조적 rebalancing 수요 — 어디서 어디로 옮겨야 하는지의 크기.",
        },
        {
            "kpi": "service level (충족률)",
            "formula": "realized / (realized + shortage)",
            "source": "ledger",
            "claim_status": "simulated",
            "business": "핵심 사업 KPI — 충족된 수요 비율. 예측→rebalancing 개선의 최종 성과.",
        },
        {
            "kpi": "peak 집중도",
            "formula": "peak-hour trips / total (또는 peak/mean)",
            "source": "trip history",
            "claim_status": "measured",
            "business": "첨두 부하 — 재배치·요금 타이밍 설계 근거.",
        },
    ]


def main() -> int:
    stamp = datetime.now(UTC)
    data_dir = Path("data/raw/nyc")
    if not list(data_dir.glob("*.zip")):
        data_dir = Path("data/raw/citibike")  # fallback: whatever trips are present
    util = utilization_kpis(data_dir)
    inv = inventory_kpis(Path("data/fixtures/gbfs_station_status.json"))
    svc = service_level_kpis(Path("reports/v2/ledger/profit_regret.json"))

    report = {
        "run_id": f"run_v2_kpi_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/monitoring/operational_kpis.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": stamp.isoformat(),
        "trip_source": str(data_dir),
        "proposed_kpi_taxonomy": taxonomy(),
        "utilization": util,
        "inventory": inv,
        "service_level": svc,
        "note": (
            "예측 metric(WAPE)만으로 못 보는 운영/사업 KPI를 source별로 정직하게 계산. "
            "utilization·imbalance는 measured(trip), 재고는 GBFS 실시간(fixture=demo), "
            "service level은 ledger(simulated)."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("V2 운영 KPI\n" + "=" * 12)
    if "n_trips" in util:
        print(
            f"[사용율] {data_dir}: {util['n_trips']:,} trips / {util['n_days']}일 / "
            f"{util['n_active_stations']} stations"
        )
        print(
            f"  daily_trips={util['daily_trips']:,} · trips/station/day={util['trips_per_active_station_per_day']} "
            f"· one_way={util['one_way_ratio']} · imbalance={util['net_flow_imbalance_index']} "
            f"· peak_share={util['peak_hour_share']}"
        )
    print(
        f"[재고] {inv.get('n_stations')} stations (demo): stockout={inv.get('stockout_rate')} "
        f"full={inv.get('full_rate')} fill={inv.get('mean_fill_ratio')}"
    )
    pm = svc.get("by_policy", {}).get("promoted_model", {})
    print(
        f"[service] promoted fill_rate={pm.get('fill_rate')} unmet={pm.get('unmet_demand_rate')} (simulated)"
    )
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
