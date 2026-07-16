"""Filter the raw NYC Permitted Events dump down to demand-relevant events (CLAUDE.md §7.4).

The NYC Open Data "Permitted Event Information" export is dominated by youth/adult sports permits
(little-league games etc.) that do not shift bike-share demand. This streams the big raw JSON array
and keeps only genuine mobility shocks — street/sidewalk/plaza closures plus parades, street fairs,
farmers markets, plaza events, filming (production) and religious processions — writing a compact
UTF-8 JSONL that is small enough to commit and feed the event pipeline.

Streaming (ijson) keeps memory flat on a 1.5 GB input; without ijson it falls back to a full load
(needs RAM). No fabrication: records are passed through unchanged, only filtered.

    python scripts/filter_permitted_events.py <raw_events.json> [out.jsonl]
    # default out: data/fixtures/nyc_permitted_events_filtered.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Event types that are pure sport permits — dropped (no street closure, no crowd-draw for cycling).
_DROP_TYPE_PREFIXES = ("sport",)

# Event types kept even without a street closure (they draw crowds / alter mobility).
_KEEP_TYPES = {
    "parade",
    "street event",
    "farmers market",
    "plaza partner event",
    "production event",
    "religious event",
}


def is_demand_relevant(e: dict) -> bool:
    """True for events that plausibly shift local bike demand (closures / crowd-draws)."""
    etype = (e.get("event_type") or "").strip().lower()
    closure = (e.get("street_closure_type") or "N/A").strip()
    if any(etype.startswith(p) for p in _DROP_TYPE_PREFIXES):
        return False  # youth/adult sports
    if closure and closure.upper() != "N/A":
        return True  # any real street/sidewalk/plaza/curb closure
    return etype in _KEEP_TYPES


def _iter_records(path: Path):
    """Yield records from a big JSON array, streaming with ijson when available."""
    try:
        import ijson  # optional; pip install ijson

        with path.open("rb") as f:
            yield from ijson.items(f, "item")
    except ImportError:
        print("[note] ijson not installed — loading the whole file (needs RAM). "
              "For a 1.5 GB input: pip install ijson", file=sys.stderr)
        with path.open(encoding="utf-8") as f:
            yield from json.load(f)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        "data/fixtures/nyc_permitted_events_filtered.jsonl"
    )
    if not src.exists():
        print(f"input not found: {src}")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)

    kept = total = 0
    kept_types: Counter[str] = Counter()
    months: Counter[str] = Counter()
    with out.open("w", encoding="utf-8") as w:
        for e in _iter_records(src):
            total += 1
            if is_demand_relevant(e):
                w.write(json.dumps(e, ensure_ascii=False) + "\n")
                kept += 1
                kept_types[e.get("event_type", "?")] += 1
                months[(e.get("start_date_time") or "")[:7]] += 1

    print(f"kept {kept} / {total} events -> {out}")
    print(f"kept types: {kept_types.most_common(12)}")
    print(f"month coverage: {sorted(months.items())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
