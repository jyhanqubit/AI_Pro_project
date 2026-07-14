"""V1-01 news backfill demo: fixture provider → coverage report + gate (offline).

    python -m pipelines.collectors.backfill_demo   # -> reports/v1/backfill/coverage.json

Real GDELT is disabled offline (BLOCKED_DATA for the real-news claim); this runs the deterministic
fixture path and prints the coverage gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from config.backfill import BackfillConfig
from pipelines.collectors.backfill import FixtureNewsProvider, backfill_news
from pipelines.collectors.coverage import coverage_gate, coverage_report

_ROOT = Path(__file__).resolve().parents[2]
_NEWS = _ROOT / "data" / "fixtures" / "news_demo.jsonl"
_OUT = _ROOT / "reports" / "v1" / "backfill" / "coverage.json"


def main() -> int:
    cfg = BackfillConfig(checkpoint_dir=str(_ROOT / "data" / "processed" / "backfill"))
    res = backfill_news(FixtureNewsProvider(_NEWS), cfg)
    rep = coverage_report(res.report)
    gate = coverage_gate(rep, cfg)

    payload = {
        "provider": res.report.provider,
        "coverage": rep.as_dict(),
        "gate_passed": gate.passed,
        "gate_reasons": gate.reasons,
        "real_news_claim": "BLOCKED_DATA (offline; GDELT disabled — no fabricated news)",
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"provider={res.report.provider}  raw={rep.raw_article_count}  "
          f"candidate={rep.candidate_article_count}  accepted={rep.accepted_count}  "
          f"sources={rep.unique_source_count}")
    print(f"coverage gate passed: {gate.passed}  {gate.reasons or ''}")
    print("real-news accuracy claim: BLOCKED_DATA (GDELT offline; fixture path only)")
    print(f"wrote {_OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
