"""V2-00 Audit & Domain Correction — a real, runnable audit check.

Run: ``python -m scripts.v2_audit`` (or ``make v2-audit``). Exit code is non-zero if any gate
fails, so CI / the phase gate can depend on it.

Gates:

1. **Domain correction** — no Seoul / Gwanak / ParcelFlow / parcel-logistics drift terms in
   active code or docs (the addendum forbids inventing a new domain). The addendum file itself
   is excluded because it names the terms only to forbid them.
2. **Result-envelope contract** — ``contracts.v2.ResultEnvelope`` and the 9-value
   ``ClaimStatus`` import and expose the mandated fields.

The stale-number reconciliation is a human-reviewed table in ``reports/v2/final/v2_audit.md``;
this script only enforces the two machine-checkable gates.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Domain-drift terms that must not appear in active code/docs (case-insensitive).
DRIFT_TERMS = [
    "seoul",
    "gwanak",
    "parcelflow",
    "parcel",
    "택배",
    "관악",
    "서울",
    "물동량",
]
DRIFT_RE = re.compile("|".join(re.escape(t) for t in DRIFT_TERMS), re.IGNORECASE)

SCAN_SUFFIXES = {".py", ".md", ".ts", ".tsx", ".yaml", ".yml", ".json", ".toml"}
# Directories never scanned (vendored, generated, or VCS internals).
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next", ".mypy_cache", ".ruff_cache"}
# Paths excluded from the drift gate because they are V2 *meta* documents that legitimately name
# the forbidden terms to state/enforce the prohibition — they are not product surfaces.
EXCLUDE_PREFIXES = (
    "CLAUDE_V2_APPEND_REVISED.md",  # names the terms only to forbid them
    "scripts/v2_audit.py",  # this file defines the term list
    "docs/v2/",  # the V2 plan docs restate the prohibition
    "reports/v2/",  # V2 audit/report artifacts quote the gate
)


def _iter_files():
    for path in REPO_ROOT.rglob("*"):
        if path.suffix not in SCAN_SUFFIXES or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith(EXCLUDE_PREFIXES):
            continue
        yield path, rel


def gate_domain_correction() -> list[str]:
    """Return a list of 'file:line: text' hits for drift terms (empty == pass)."""
    hits: list[str] = []
    for path, rel in _iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if DRIFT_RE.search(line):
                hits.append(f"{rel}:{lineno}: {line.strip()[:120]}")
    return hits


def gate_result_envelope() -> list[str]:
    """Return a list of contract problems (empty == pass)."""
    problems: list[str] = []
    try:
        from contracts.v2 import ClaimStatus, ResultEnvelope
    except Exception as exc:  # noqa: BLE001 — audit reports the failure, does not swallow it
        return [f"contracts.v2 import failed: {exc!r}"]

    expected_statuses = {
        "measured",
        "offline_benchmark",
        "simulated",
        "pending_live_label",
        "assumption",
        "blocked_data",
        "blocked_external",
        "demo_fixture",
        "research",
    }
    actual = {s.value for s in ClaimStatus}
    if actual != expected_statuses:
        problems.append(f"ClaimStatus mismatch: {sorted(actual)} != {sorted(expected_statuses)}")

    required_fields = {"value", "run_id", "artifact_id", "mode", "claim_status", "freshness"}
    missing = required_fields - set(ResultEnvelope.model_fields)
    if missing:
        problems.append(f"ResultEnvelope missing fields: {sorted(missing)}")
    return problems


def main() -> int:
    print("V2-00 Audit & Domain Correction\n" + "=" * 34)

    drift = gate_domain_correction()
    print(f"\n[1] Domain correction gate: {'PASS' if not drift else 'FAIL'}")
    if drift:
        for h in drift:
            print(f"    drift: {h}")

    envelope = gate_result_envelope()
    print(f"[2] Result-envelope contract gate: {'PASS' if not envelope else 'FAIL'}")
    if envelope:
        for p in envelope:
            print(f"    problem: {p}")

    ok = not drift and not envelope
    print(f"\nV2-00 audit: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
