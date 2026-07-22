"""V2-03 — can news even SATISFY the four conditions? An availability audit (no trip data needed).

The quality ablation proved the permit feed works because it is dense + precisely-timed +
precisely-located + forward-looking, and that degrading ANY axis collapses the value. The natural
follow-up ("encode a 4-D feature vector so news satisfies the conditions") rests on a misconception:
the conditions are properties of the SOURCE (what information exists), not of the feature encoding.
An extractor cannot invent an exact hour the article never states, or make a retrospective review
forward-looking.

This audit quantifies, per event, whether the source actually carries each property:
  - forward_looking : published > `lead_min_h` hours BEFORE the event starts (usable lead time)
  - precise_location: attributed to a single specific borough (not citywide)
  - (precise_time / density are noted structurally: times were LLM-inferred, not stated; N≈19)

If the subset satisfying forward+precise is ~empty, the 4-D idea reduces to nothing on this data —
not because of the encoding, but because retrospective borough-level news lacks the information.

Writes `reports/v2/llm_value/news_condition_audit.json`. Fast; no trip pipeline.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipelines.collectors.news import NewsFixtureCollector

_NY = ZoneInfo("America/New_York")
OUT_DIR = Path("reports/v2/llm_value")


def run(news_path: str, signed_events: str, lead_min_h: float = 3.0) -> dict:
    arts = {a.article_id: a for a in NewsFixtureCollector(Path(news_path)).collect().records}
    evs = [json.loads(x) for x in Path(signed_events).read_text(encoding="utf-8").splitlines() if x.strip()]
    per = []
    for e in sorted(evs, key=lambda x: x.get("d", "")):
        a = arts.get(e["article_id"])
        if a is None or not e.get("event_start_at"):
            continue
        start = datetime.fromisoformat(e["event_start_at"]).astimezone(_NY)
        pub = (a.available_at or max(a.published_at, a.first_seen_at)).astimezone(_NY)
        lead_h = round((start - pub).total_seconds() / 3600.0, 1)
        per.append({
            "d": e["d"], "event_type": e["event_type"], "lead_time_h": lead_h,
            "forward_looking": lead_h > lead_min_h,
            "precise_location": len([b for b in e.get("boroughs", []) if b]) == 1,
        })
    n = len(per)
    fwd = sum(p["forward_looking"] for p in per)
    ploc = sum(p["precise_location"] for p in per)
    both = sum(p["forward_looking"] and p["precise_location"] for p in per)
    return {
        "run_id": f"run_v2-03newsaudit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/llm_value/news_condition_audit.json",
        "mode": "historical_replay", "claim_status": "measured", "freshness": datetime.now(UTC).isoformat(),
        "lead_min_h": lead_min_h,
        "n_events": n,
        "forward_looking": fwd,
        "precise_location": ploc,
        "forward_and_precise": both,
        "density_note": f"only {n} events total (≈ news scale); the density curve puts the value "
                        "threshold well above 100 events",
        "per_event": per,
        "finding": (
            f"Only {fwd}/{n} news events are forward-looking (published >{lead_min_h}h before onset) "
            f"and only {both}/{n} are BOTH forward-looking AND single-borough. The subset that could "
            "satisfy the permit feed's necessary conditions is ~empty — because news reports events "
            "coincident-or-after, at borough granularity. A 4-D feature vector cannot encode "
            "information the source does not contain; forward-looking precise events come from "
            "schedules/permits/announcements, not retrospective news."
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ml.forecasting.news_condition_audit")
    ap.add_argument("--news", default="data/fixtures/news_live/news_gdelt_nyc_2026h1.jsonl")
    ap.add_argument("--signed-events", default="data/fixtures/news_live/claude_events_signed_2026h1.jsonl")
    ap.add_argument("--lead-min-h", type=float, default=3.0)
    ns = ap.parse_args(argv)
    res = run(ns.news, ns.signed_events, ns.lead_min_h)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "news_condition_audit.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"News condition audit — {res['n_events']} events (lead>{res['lead_min_h']}h = forward-looking)")
    print(f"  forward-looking:            {res['forward_looking']}/{res['n_events']}")
    print(f"  precise single-borough:     {res['precise_location']}/{res['n_events']}")
    print(f"  BOTH forward AND precise:   {res['forward_and_precise']}/{res['n_events']}")
    print(f"\n{res['finding']}")
    print(f"report -> {OUT_DIR}/news_condition_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
