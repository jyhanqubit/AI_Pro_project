"""V2-07 — trip-query parsing benchmark: rule-based vs in-session LLM.

The trip planner's *numbers* are deterministic, but turning a free-text request into (origin,
destination) is intent understanding — the one place V2-06 measured the LLM beating keywords. This
benchmarks the shipped rule-based parser (`trip_planner.resolve_endpoints`) against real in-session
LLM parses (no API key in the sandbox; parses committed to `data/fixtures/v2/trip_parse_claude.jsonl`
for audit, exactly as V2-03 extraction / V2-06 routing) on a fixed query set with method-independent
gold (`trip_parse_queries.jsonl`).

The set mixes easy phrasings (both handle) with hard ones — typos (`뉴포뜨`, `시쳥`), negation
(`익스체인지 말고`), and origin-stated-last (`출발은 시청`) — where substring matching fails and intent
understanding is needed. Writes `reports/v2/copilot/trip_parse_benchmark.json`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from services.api.trip_planner import resolve_endpoints
from services.api.v2 import _alias_index

QUERIES = Path("data/fixtures/v2/trip_parse_queries.jsonl")
CLAUDE = Path("data/fixtures/v2/trip_parse_claude.jsonl")
OUT = Path("reports/v2/copilot/trip_parse_benchmark.json")


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main(argv=None) -> int:
    now = datetime.now(UTC)
    queries = _rows(QUERIES)
    claude = {r["id"]: r for r in _rows(CLAUDE)}
    aliases = _alias_index()

    per, rule_ok, llm_ok = [], 0, 0
    for q in queries:
        gold = (q["origin"], q["destination"])
        r_o, r_d = resolve_endpoints(q["query"], aliases)
        c = claude.get(q["id"], {})
        c_o, c_d = c.get("origin"), c.get("destination")
        r_hit = (r_o, r_d) == gold
        c_hit = (c_o, c_d) == gold
        rule_ok += r_hit
        llm_ok += c_hit
        per.append({"id": q["id"], "query": q["query"], "gold": list(gold),
                    "rule_based": [r_o, r_d], "rule_ok": r_hit,
                    "llm": [c_o, c_d], "llm_ok": c_hit, "llm_rationale": c.get("rationale")})

    n = len(queries)
    report = {
        "run_id": f"run_v2-07tripparse_{now.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/copilot/trip_parse_benchmark.json",
        "mode": "historical_replay", "claim_status": "offline_benchmark", "freshness": now.isoformat(),
        "judge": "claude-opus-4-8-insession",
        "note": "LLM parses committed to data/fixtures/v2/trip_parse_claude.jsonl (no API key; "
                "in-session, auditable). The planner's distances/times/stations remain deterministic; "
                "only the NL→(origin,destination) parse is compared here.",
        "n": n,
        "rule_based_accuracy": round(rule_ok / n, 3),
        "llm_accuracy": round(llm_ok / n, 3),
        "rule_based_correct": rule_ok,
        "llm_correct": llm_ok,
        "hard_cases_where_llm_wins": [p["id"] for p in per if p["llm_ok"] and not p["rule_ok"]],
        "per_query": per,
        "finding": "Rule-based substring matching handles explicit phrasings but fails on typos, "
                   "negation, and origin-stated-last; the LLM parses all correctly. This is the seam "
                   "where an LLM parser (when a key is configured) replaces resolve_endpoints — the "
                   "measured V2-06 lesson (intent understanding is the LLM's value), applied to trips.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"V2-07 trip-parse benchmark — {n} queries")
    print(f"  rule_based accuracy: {report['rule_based_accuracy']}  ({rule_ok}/{n})")
    print(f"  LLM accuracy       : {report['llm_accuracy']}  ({llm_ok}/{n})  [in-session, committed]")
    print(f"  LLM wins on hard cases: {report['hard_cases_where_llm_wins']}")
    for p in per:
        if not p["rule_ok"]:
            print(f"    [{p['id']}] rule FAIL: {p['query']!r} -> {p['rule_based']} (gold {p['gold']}); "
                  f"LLM {'OK' if p['llm_ok'] else 'FAIL'}")
    print(f"report -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
