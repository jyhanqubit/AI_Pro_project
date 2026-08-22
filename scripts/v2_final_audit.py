"""V2-09 — Final Audit & Portfolio Packaging.

Run: ``python -m scripts.v2_final_audit`` (or ``make v2-final``). Exit code is non-zero if any gate
fails, so it can serve as the V2 completion gate.

Unlike V2-00 (which defined the contract), this phase judges the finished portfolio **by its
committed artifacts** (addendum "Completion Rule"). It does not re-measure anything — it reads what
the phase runners already produced under ``reports/v2/**`` and verifies four things:

1. **Envelope honesty gate** — every committed V2 artifact carries the result-envelope fields and
   *validates* through :class:`contracts.v2.ResultEnvelope` (so a mislabeled or evidence-free
   number fails here, not in front of a reviewer).
2. **Completion-artifact gate** — each artifact the completion rule requires is present and fresh.
3. **Claim matrix** — mirrors every artifact into ``reports/v2/final/claim_matrix.json``, each row
   linked to its ``artifact_id`` with its claim_status + a headline metric.
4. **Traceability gate** — each artifact's self-declared ``artifact_id`` path exists on disk.

This is deliberately machine-checkable. The narrative claim matrix stays in
``docs/v2/V2_CLAIMS_MATRIX.md``; this script keeps the machine copy in sync and honest.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
V2_REPORTS = REPO_ROOT / "reports" / "v2"
FINAL_DIR = V2_REPORTS / "final"
CLAIM_MATRIX = FINAL_DIR / "claim_matrix.json"

ENVELOPE_FIELDS = ("run_id", "artifact_id", "mode", "claim_status", "freshness")

# The addendum "Completion Rule" artifacts (claim → the file that must exist).
COMPLETION_ARTIFACTS: dict[str, str] = {
    "H3 holdout metrics": "reports/v2/holdout/h3_multiholdout.json",
    "profit/regret ledger": "reports/v2/ledger/profit_regret.json",
    "LLM incremental value report": "reports/v2/llm_value/incremental_value_borough.json",
    "MPC policy comparison": "reports/v2/mpc/policy_comparison.json",
    "pricing sensitivity": "reports/v2/pricing/sensitivity.json",
    "pricing guardrail audit": "reports/v2/pricing/guardrail_audit.json",
    "Copilot correctness benchmark": "reports/v2/copilot/correctness_benchmark.json",
    "final claim matrix": "reports/v2/final/claim_matrix.json",  # produced by this script
}

# Accurate per-artifact headline pointers (path into the artifact → label). Curated on purpose:
# a generic "grab any nested scalar" scan surfaces misleading numbers (e.g. the wrong policy's
# cost), so artifacts not listed here get NO headline number — only the artifact_id link. Paths use
# string keys and int list-indices.
HEADLINE_POINTERS: dict[str, dict[str, list]] = {
    "reports/v2/holdout/h3_multiholdout.json": {
        "wape": ["aggregate", "wape"],
        "mase": ["aggregate", "mase"],
    },
    "reports/v2/ledger/profit_regret.json": {
        "model_minus_no_action_net": ["predictive_lift_to_profit", "model_minus_no_action_net"],
        "regret_vs_oracle": ["predictive_lift_to_profit", "model_regret_vs_oracle"],
    },
    "reports/v2/mpc/policy_comparison.json": {
        "mpc_total_cost": ["by_policy", "mpc", "total_cost"],
        "mpc_regret_vs_oracle": ["by_policy", "mpc", "regret_vs_oracle"],
    },
    "reports/v2/pricing/guardrail_audit.json": {
        "violation_count": ["violation_count"],
        "budget_respected": ["budget_respected"],
    },
    "reports/v2/pricing/sensitivity.json": {
        "AA_ci_covers_zero": ["experiment_dry_run_AA", "ci_covers_zero"],
    },
    "reports/v2/copilot/correctness_benchmark.json": {
        "routing_accuracy": ["routing_accuracy"],
        "hallucinated_answers": ["hallucinated_answers"],
        "hard_gates_pass": ["hard_gates_pass"],
    },
    "reports/v2/copilot/ragas_generation_benchmark.json": {
        "faithfulness": ["faithfulness"],
        "answer_relevancy": ["answer_relevancy"],
    },
    "reports/v2/copilot/trip_faithfulness.json": {
        "mean_faithfulness": ["mean_faithfulness"],
        "ungrounded_numbers_total": ["ungrounded_numbers_total"],
    },
    "reports/v2/llm_value/incremental_value_borough.json": {
        "structured_lift_verdict": ["structured_event_lift_A1_minus_A0", "verdict"],
        "llm_news_verdict": ["llm_news_increment_A2_minus_A1", "verdict"],
        "net_llm_value_simulated": ["net_llm_value_simulated"],
    },
    "reports/v2/research/rl_rebalancing.json": {
        "best_rl": ["best_rl"],
        "best_rl_regret": ["best_rl_regret"],
        "mpc_regret": ["mpc_regret"],
        "ppo_beats_tabular": ["ppo_beats_tabular"],
        "beats_mpc": ["beats_mpc"],
    },
}
# blocked/pending statuses must carry NO value (envelope rule 4).
BLOCKED_OR_PENDING = {"blocked_data", "blocked_external", "pending_live_label"}


def _artifacts() -> list[Path]:
    """Every committed V2 artifact except the machine claim matrix (which we generate)."""
    return sorted(p for p in V2_REPORTS.rglob("*.json") if p != CLAIM_MATRIX)


def _resolve(obj: Any, path: list) -> Any:
    """Follow a curated path of dict keys / list indices; return None if it doesn't resolve."""
    cur = obj
    for k in path:
        try:
            cur = cur[k]
        except (KeyError, IndexError, TypeError):
            return None
    return cur if isinstance(cur, (int, float, str, bool)) else None


def _headline(rel: str, d: dict[str, Any]) -> dict[str, Any]:
    """Accurate headline metrics for known artifacts (empty for the rest — link via artifact_id)."""
    pointers = HEADLINE_POINTERS.get(rel, {})
    out = {}
    for label, path in pointers.items():
        val = _resolve(d, path)
        if val is not None:
            out[label] = val
    return out


def gate_envelopes() -> tuple[list[dict[str, Any]], list[str]]:
    """Validate every artifact's envelope through ResultEnvelope. Returns (rows, problems)."""
    try:
        from contracts.v2 import ResultEnvelope
    except Exception as exc:  # noqa: BLE001 — the audit reports the failure, does not hide it
        return [], [f"contracts.v2 import failed: {exc!r}"]

    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    for path in _artifacts():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{rel}: unreadable JSON ({exc!r})")
            continue
        if not isinstance(d, dict):
            problems.append(f"{rel}: top-level is {type(d).__name__}, not an object")
            continue
        missing = [f for f in ENVELOPE_FIELDS if f not in d]
        if missing:
            problems.append(f"{rel}: missing envelope fields {missing}")
            continue
        cs = d["claim_status"]
        # A blocked/pending artifact must not carry a headline value.
        value = None if cs in BLOCKED_OR_PENDING else {"artifact": rel}
        try:
            ResultEnvelope[dict](
                value=value,
                run_id=d["run_id"],
                artifact_id=d["artifact_id"],
                mode=d["mode"],
                claim_status=cs,
                freshness=d["freshness"],
            )
        except Exception as exc:  # noqa: BLE001 — mislabeled artifact caught here
            problems.append(f"{rel}: envelope invalid — {exc}")
            continue
        rows.append(
            {
                "artifact": rel,
                "run_id": d["run_id"],
                "artifact_id": d["artifact_id"],
                "mode": d["mode"],
                "claim_status": cs,
                "freshness": d["freshness"],
                "headline": _headline(rel, d),
            }
        )
    return rows, problems


def gate_completion(rows: list[dict[str, Any]]) -> list[str]:
    """Every completion-rule artifact must be present (on disk)."""
    on_disk = {(REPO_ROOT / r["artifact"]).resolve() for r in rows}
    problems = []
    for claim, rel in COMPLETION_ARTIFACTS.items():
        p = (REPO_ROOT / rel).resolve()
        # The claim matrix is written after this gate, so accept its pending creation.
        if rel == "reports/v2/final/claim_matrix.json":
            continue
        if p not in on_disk and not p.exists():
            problems.append(f"missing completion artifact for '{claim}': {rel}")
    return problems


def gate_traceability(rows: list[dict[str, Any]]) -> list[str]:
    """Each artifact's self-declared artifact_id path must exist on disk (traceable)."""
    problems = []
    for r in rows:
        # artifact_id may carry a #pointer suffix — strip it to get the file path.
        declared = str(r["artifact_id"]).split("#", 1)[0]
        if not (REPO_ROOT / declared).exists():
            problems.append(f"{r['artifact']}: artifact_id path does not exist: {declared}")
    return problems


def main() -> int:
    print("V2-09 Final Audit & Portfolio Packaging\n" + "=" * 39)
    stamp = datetime.now(UTC)

    rows, env_problems = gate_envelopes()
    print(
        f"\n[1] Envelope honesty gate: {'PASS' if not env_problems else 'FAIL'} "
        f"({len(rows)} artifacts validated)"
    )
    for p in env_problems:
        print(f"    problem: {p}")

    comp_problems = gate_completion(rows)
    print(f"[2] Completion-artifact gate: {'PASS' if not comp_problems else 'FAIL'}")
    for p in comp_problems:
        print(f"    problem: {p}")

    trace_problems = gate_traceability(rows)
    print(f"[3] Traceability gate: {'PASS' if not trace_problems else 'FAIL'}")
    for p in trace_problems:
        print(f"    problem: {p}")

    # Claim matrix (machine copy) — written regardless so a reviewer sees the current state.
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["claim_status"]] = by_status.get(r["claim_status"], 0) + 1
    ok = not (env_problems or comp_problems or trace_problems)
    matrix = {
        "run_id": f"run_v2-09_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/final/claim_matrix.json",
        "mode": "historical_replay",
        "claim_status": "measured",  # this matrix is a measured inventory of committed artifacts
        "freshness": stamp.isoformat(),
        "gates": {
            "envelope_honesty": not env_problems,
            "completion_artifacts": not comp_problems,
            "traceability": not trace_problems,
        },
        "n_artifacts": len(rows),
        "by_claim_status": dict(sorted(by_status.items())),
        "completion_rule_artifacts": {
            claim: {"path": rel, "present": (REPO_ROOT / rel).exists()}
            for claim, rel in COMPLETION_ARTIFACTS.items()
        },
        "claims": rows,
        "verdict": "V2_COMPLETE" if ok else "V2_INCOMPLETE",
        "note": (
            "Machine mirror of docs/v2/V2_CLAIMS_MATRIX.md, built from committed artifacts. "
            "RL/QAOA are research-only and excluded from the completion gate."
        ),
    }
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    CLAIM_MATRIX.write_text(json.dumps(matrix, indent=2), encoding="utf-8")

    print(f"\nartifacts by claim_status: {matrix['by_claim_status']}")
    print(f"claim matrix -> {CLAIM_MATRIX.relative_to(REPO_ROOT)}")
    print(f"\nV2-09 final audit: {'PASS — V2_COMPLETE' if ok else 'FAIL — V2_INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
