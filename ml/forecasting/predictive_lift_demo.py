"""Offline predictive-lift run on the demo fixture (V2-02). CLAUDE.md §11, §22.

Runs the coverage gate over the curated demo data and reports the honest verdict. The demo news
fixture has only a couple of events over three zones — far below the V2-01 coverage gate — so the
predictive-lift claim is ``blocked_data`` and stays disabled. No paired M0/M1 error comparison is
fabricated; the protocol machinery itself is validated separately in ``tests/unit`` on synthetic
data with known lift / no-lift / negative-lift cases.

Passing the gate (and enabling a measured claim) requires a real overlapping-news backfill and a
training run — that path is blocked in this offline environment, and this report says so plainly.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from config.api import DEMO_END, DEMO_START
from config.collectors import NEWS_DEMO_FIXTURE
from contracts.enums import ExtractionStatus
from pipelines.events import build_provider, extract_events
from pipelines.features import GraphFeatureConfig, build_graph_features

from .predictive_lift import lift_verdict

# V2-01 coverage gate thresholds (a lift claim is only allowed once these are met).
GATE = {
    "min_unique_events": 20,
    "min_affected_zone_hours": 200,
    "min_unique_sources": 5,
    "min_event_types": 3,
}


def _load_articles():
    from pipelines.collectors import NewsFixtureCollector

    return NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records


def event_coverage() -> dict:
    """Real coverage of the demo fixture: unique events/sources/types + affected zone-hours."""
    articles = _load_articles()
    events, _ = extract_events(articles, build_provider("mock"))
    accepted = [e for e in events if e.status is ExtractionStatus.ACCEPTED]

    cfg = GraphFeatureConfig()
    # Affected zone-hours: at each hourly cutoff, zones with nonzero event exposure.
    zones_all = sorted(
        {s.zone_id for s in build_graph_features(accepted, articles, forecast_cutoff=DEMO_END)}
    )
    affected_zone_hours = 0
    cutoff = DEMO_START
    while cutoff <= DEMO_END:
        avail = [e for e in accepted if e.available_at is not None and e.available_at <= cutoff]
        snaps = build_graph_features(
            avail, articles, forecast_cutoff=cutoff, zones=zones_all, config=cfg
        )
        affected_zone_hours += sum(
            1 for s in snaps if float(s.features.get("distance_decayed_impact", 0.0)) > 0.0
        )
        cutoff = cutoff + timedelta(hours=1)

    sources = {a.source for a in articles}
    types = {str(e.event_type) for e in accepted}
    return {
        "unique_events": len(accepted),
        "unique_sources": len(sources),
        "event_types": len(types),
        "affected_zone_hours": affected_zone_hours,
    }


def run() -> dict:
    cov = event_coverage()
    conditions = {
        "unique_events": cov["unique_events"] >= GATE["min_unique_events"],
        "affected_zone_hours": cov["affected_zone_hours"] >= GATE["min_affected_zone_hours"],
        "unique_sources": cov["unique_sources"] >= GATE["min_unique_sources"],
        "event_types": cov["event_types"] >= GATE["min_event_types"],
    }
    coverage_ok = all(conditions.values())

    # No paired M0/M1 comparison is run here: without a passing coverage gate (and with no trained
    # models offline) any gain would be uninformative. The verdict is derived honestly.
    verdict = lift_verdict(0.0, 0.0, 0.0, coverage_ok=coverage_ok)

    return {
        "protocol": "predictive-lift-v2",
        "coverage": cov,
        "coverage_gate": GATE,
        "coverage_conditions": conditions,
        "coverage_ok": coverage_ok,
        **verdict,
        "note": (
            "데모 fixture는 커버리지 게이트(이벤트/소스/타입/영향 zone-hour)에 크게 못 미쳐 "
            "predictive lift 주장은 blocked_data로 비활성입니다. 측정된 lift는 실제 겹치는 뉴스 "
            "backfill + 학습이 통과해야 가능하며(V2-01/V2-02), 이 오프라인 환경에서는 차단됩니다. "
            "프로토콜(시계열 분할·purge/embargo·이벤트 블록 부트스트랩 CI·판정 규칙)은 "
            "tests/unit/test_predictive_lift.py에서 합성 데이터로 검증됩니다."
        ),
    }


def main() -> None:
    report = run()
    out_dir = Path("reports/v2")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "predictive_lift.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# V2-02 Predictive Lift — Coverage Report",
        "",
        f"- verdict: **{report['verdict']}** (claim_enabled={report['claim_enabled']})",
        f"- coverage_ok: {report['coverage_ok']}",
        f"- unique_events: {report['coverage']['unique_events']} "
        f"(gate ≥ {GATE['min_unique_events']})",
        f"- affected_zone_hours: {report['coverage']['affected_zone_hours']} "
        f"(gate ≥ {GATE['min_affected_zone_hours']})",
        f"- unique_sources: {report['coverage']['unique_sources']} "
        f"(gate ≥ {GATE['min_unique_sources']})",
        f"- event_types: {report['coverage']['event_types']} (gate ≥ {GATE['min_event_types']})",
        "",
        report["note"],
    ]
    (out_dir / "predictive_lift.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
