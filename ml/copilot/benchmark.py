"""V2-06 runner: ``python -m ml.copilot.benchmark`` (make v2-copilot).

Scores the typed-tool Copilot against the fixed offline question set
(`data/fixtures/v2/copilot_questions.jsonl`) on: tool-routing accuracy, correctness (answer matches
the tool's grounded ground truth), grounding (every numeric answer cites an artifact), refusal
accuracy (unanswerable questions are refused, not guessed), and the two HARD gates —
``ungrounded_numeric_answers == 0`` and ``hallucinated_answers == 0``.

Hallucination here = a numeric answer to a question that should have been refused. By construction
the Copilot cannot emit a number without a tool result, so these gates should hold; the benchmark
verifies it (and would catch a regression in the router that fabricates an answer).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ml.copilot.copilot import answer

QUESTIONS = Path("data/fixtures/v2/copilot_questions.jsonl")
OUT_DIR = Path("reports/v2/copilot")


def _matches(value, truth) -> bool:
    if isinstance(truth, (int, float)) and isinstance(value, (int, float)):
        return abs(float(value) - float(truth)) <= 1e-2 + 1e-3 * abs(float(truth))
    return str(value) == str(truth)


def main(argv=None) -> int:
    stamp = datetime.now(UTC)
    rows = [json.loads(x) for x in QUESTIONS.read_text(encoding="utf-8").splitlines() if x.strip()]

    per_q = []
    answerable = [r for r in rows if r["expected_tool"] is not None]
    refuse = [r for r in rows if r["expected_tool"] is None]
    routing_ok = correct = grounded_num = 0
    correct_refusals = hallucinated = ungrounded_numeric = 0

    for r in rows:
        a = answer(r["question"])
        exp = r["expected_tool"]
        rec = {"id": r["id"], "answered": a.answered, "tool": a.tool,
               "value": a.value, "artifact_id": a.artifact_id, "expected_tool": exp}
        if exp is not None:  # answerable
            if a.answered and a.tool == exp:
                routing_ok += 1
            if a.answered and _matches(a.value, r["ground_truth"]):
                correct += 1
                rec["correct"] = True
            else:
                rec["correct"] = False
            if a.answered and a.is_numeric:
                if a.artifact_id:
                    grounded_num += 1
                else:
                    ungrounded_numeric += 1
        else:  # should refuse
            if not a.answered:
                correct_refusals += 1
                routing_ok += 1
                rec["correct_refusal"] = True
            else:
                rec["correct_refusal"] = False
                if a.is_numeric:
                    hallucinated += 1  # numeric answer to an unanswerable question
        per_q.append(rec)

    n_ans = len(answerable)
    n_ref = len(refuse)
    n_num_answered = sum(1 for r in per_q if r.get("answered") and isinstance(r.get("value"), (int, float)))

    report = {
        "run_id": f"run_v2-06_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/copilot/correctness_benchmark.json",
        "mode": "research", "claim_status": "offline_benchmark", "freshness": stamp.isoformat(),
        "question_set": str(QUESTIONS), "n_questions": len(rows),
        "n_answerable": n_ans, "n_should_refuse": n_ref,
        "routing_accuracy": round(routing_ok / len(rows), 3),
        "correctness_accuracy": round(correct / n_ans, 3) if n_ans else None,
        "refusal_accuracy": round(correct_refusals / n_ref, 3) if n_ref else None,
        "grounded_ratio": round(grounded_num / n_num_answered, 3) if n_num_answered else 1.0,
        "ungrounded_numeric_answers": ungrounded_numeric,   # HARD gate == 0
        "hallucinated_answers": hallucinated,               # HARD gate == 0
        "hard_gates_pass": ungrounded_numeric == 0 and hallucinated == 0,
        "per_question": per_q,
        "note": (
            "Numbers come only from typed tools reading committed V2 artifacts (grounding by "
            "construction). Routing stands in for the LLM's tool-selection; the numeric values are "
            "never produced by the router. offline_benchmark on a fixed question set."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "correctness_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"V2-06 GraphRAG Copilot benchmark — {len(rows)} questions "
          f"({n_ans} answerable, {n_ref} should-refuse)")
    print(f"  routing_accuracy    : {report['routing_accuracy']}")
    print(f"  correctness_accuracy: {report['correctness_accuracy']}")
    print(f"  refusal_accuracy    : {report['refusal_accuracy']}")
    print(f"  grounded_ratio      : {report['grounded_ratio']}")
    print(f"  ungrounded_numeric  : {report['ungrounded_numeric_answers']} (hard gate == 0)")
    print(f"  hallucinated_answers: {report['hallucinated_answers']} (hard gate == 0)")
    print(f"  HARD GATES PASS     : {report['hard_gates_pass']}")
    print(f"report -> {OUT_DIR}/correctness_benchmark.json")
    return 0 if report["hard_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
