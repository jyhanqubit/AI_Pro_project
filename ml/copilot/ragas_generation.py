"""V2-06 — RAGAS generation-side metrics (faithfulness, answer relevancy), judged in-session.

RAGAS's distinctive metrics need an LLM judge, and there is no API key in this sandbox. Rather than
leave them `blocked_external`, we do what V2-03 (event extraction) and V2-06 (tool routing) already
do: **the model acts as the judge in-session**, and every judgment is committed as an inspectable
fixture (`data/fixtures/v2/copilot_ragas_judgments.jsonl`) so a reviewer can audit each verdict.

Metrics (RAGAS definitions):
- **faithfulness** = supported_claims / total_claims. Each Copilot answer is decomposed into atomic
  claims; each claim is verified against the RETRIEVED CONTEXT (the typed tool's result + the artifact
  value it cites). A claim not grounded in that context is unfaithful — even if true in the world.
- **answer_relevancy** = how well the answer addresses the question (0..1). NOTE: RAGAS's automated
  answer_relevancy is an embedding-similarity proxy over LLM-generated questions; we have no embedding
  model, so this is a DIRECT relevance judgment, labeled as such (not the embedding proxy).

Only the ANSWERED questions are scored — faithfulness/relevancy apply to generated answers; refusals
are graded by the separate correctness/refusal benchmark.

Honesty guards:
- **Drift guard**: the runner re-runs the live Copilot and fails if a judged answer no longer matches
  the code's current output, so judgments can never silently detach from the implementation.
- **Self-judgment caveat**: the judge and the system are the same model family (no independent LLM
  available). Judgments are committed for external audit; this is recorded in the artifact.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from ml.copilot.copilot import answer

ROUTING = Path("data/fixtures/v2/copilot_routing_claude.jsonl")
JUDGMENTS = Path("data/fixtures/v2/copilot_ragas_judgments.jsonl")
QUESTIONS = Path("data/fixtures/v2/copilot_questions.jsonl")
OUT_DIR = Path("reports/v2/copilot")
JUDGE = "claude-opus-4-8-insession"


def _norm(s: str) -> str:
    s = s.replace("—", "-").replace("–", "-").replace("−", "-")
    s = s.replace(",", "").lower()
    return re.sub(r"\s+", " ", s).strip()


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _live_answers() -> dict[str, str]:
    """Re-run the Copilot with the committed claude routing; return {qid: answer_text} for answered."""
    routes = {r["id"]: r.get("tool") for r in _rows(ROUTING)}
    questions = {r["id"]: r["question"] for r in _rows(QUESTIONS)}
    out: dict[str, str] = {}
    for qid, q in questions.items():
        tool = routes.get(qid)
        if tool is None or tool == "refuse":
            continue
        a = answer(q, route_fn=lambda _q, t=tool: t)
        if a.answered:
            out[qid] = a.text
    return out


def main(argv=None) -> int:
    stamp = datetime.now(UTC)
    judgments = _rows(JUDGMENTS)
    live = _live_answers()

    # Drift guard: every judged answer must still match the live Copilot output.
    drift = []
    for j in judgments:
        got = live.get(j["id"])
        if got is None:
            drift.append(f"{j['id']}: no longer answered by the Copilot")
        elif _norm(got) != _norm(j["answer"]):
            drift.append(f"{j['id']}: answer changed\n    judged: {j['answer']}\n    live  : {got}")
    if drift:
        raise SystemExit("RAGAS judgments are stale (re-judge after the change):\n" + "\n".join(drift))

    faiths, per = [], []
    for j in judgments:
        claims = j["claims"]
        supported = sum(1 for c in claims if c["supported"])
        f = supported / len(claims)
        faiths.append(f)
        per.append({"id": j["id"], "faithfulness": round(f, 3),
                    "supported_claims": supported, "total_claims": len(claims),
                    "answer_relevancy": j["answer_relevancy"]})
    rels = [j["answer_relevancy"] for j in judgments]
    n = len(judgments)

    report = {
        "run_id": f"run_v2-06ragasgen_{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        "artifact_id": "reports/v2/copilot/ragas_generation_benchmark.json",
        "mode": "historical_replay", "claim_status": "offline_benchmark", "freshness": stamp.isoformat(),
        "judge": JUDGE,
        "judge_note": "No LLM API key in sandbox; the model judged in-session (as in V2-03 extraction "
                      "and V2-06 routing). Every verdict is committed in "
                      "data/fixtures/v2/copilot_ragas_judgments.jsonl for audit.",
        "metric_definitions": {
            "faithfulness": "RAGAS: supported_claims / total_claims, claims verified against the "
                            "typed-tool retrieved context (value + cited artifact).",
            "answer_relevancy": "DIRECT relevance judgment (0..1). NOT RAGAS's embedding-similarity "
                                "proxy (no embedding model available); labeled as a direct judgment.",
        },
        "scope": "answered questions only (refusals graded by correctness_benchmark.json)",
        "n_answered": n,
        "faithfulness": round(sum(faiths) / n, 4),
        "answer_relevancy": round(sum(rels) / n, 4),
        "per_question": per,
        "notable": [
            "faithfulness is high BY DESIGN: the Copilot only restates typed-tool values with their "
            "artifact-backed claim_status, so answers are structurally grounded. The value of judging "
            "is catching mislabels, not raw grounding.",
            "This pass caught a real defect: llm_news_value stamped a SIMULATED dollar figure as "
            "'measured' (inherited from the artifact's top-level WAPE claim_status). Fixed to "
            "'simulated'; q08 re-scored 1.0. Without the fix q08 faithfulness was 3/4=0.75.",
        ],
        "caveats": [
            "Self-judgment: judge and system are the same model family; no independent LLM available. "
            "Verdicts are committed for external audit to mitigate this.",
            "answer_relevancy is a direct judgment, not RAGAS's embedding-based generated-question "
            "proxy — comparable in intent, not in method.",
            "Small fixed set (10 answered Q). This measures grounding discipline, not broad coverage.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "ragas_generation_benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"V2-06 RAGAS generation-side (judge={JUDGE}) — {n} answered questions")
    print(f"  faithfulness    : {report['faithfulness']}")
    print(f"  answer_relevancy: {report['answer_relevancy']}  (direct judgment, not embedding proxy)")
    print(f"  drift guard     : PASS (all {n} judged answers match live Copilot output)")
    print(f"report -> {OUT_DIR}/ragas_generation_benchmark.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
