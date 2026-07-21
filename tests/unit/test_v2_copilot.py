"""V2-06 GraphRAG Copilot tests.

The non-negotiable one: a numeric answer is emitted ONLY with a typed-tool artifact behind it;
otherwise the Copilot refuses. Plus routing, grounding, and the fixed-question-set hard gates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.copilot.copilot import answer, route
from ml.copilot.tools import REGISTRY, ToolUnavailable


def test_router_picks_specific_metric_over_generic_model():
    # "WAPE of the promoted model" mentions both -> the specific metric (WAPE) must win.
    assert route("What is the WAPE of the promoted model?") == "forecast_wape"
    assert route("Which model is served?") == "promoted_model"


def test_answerable_question_is_grounded():
    a = answer("What is the holdout WAPE?")
    assert a.answered and a.tool == "forecast_wape"
    assert a.artifact_id and a.artifact_id.startswith("reports/v2/holdout/")
    assert isinstance(a.value, float)


def test_unanswerable_question_is_refused_not_guessed():
    a = answer("What will the weather be tomorrow in Brooklyn?")
    assert a.answered is False
    assert a.value is None
    assert a.refusal_reason == "no_tool_match"


def test_no_numeric_answer_without_provenance():
    # Structural guarantee: any numeric answer carries an artifact_id.
    for q in ["holdout WAPE?", "profit vs no action?", "MPC regret?", "guardrail violations?"]:
        a = answer(q)
        if a.answered and a.is_numeric:
            assert a.artifact_id, f"{q!r} produced an ungrounded number"


def test_causal_realworld_question_refused():
    # No real users / causal data -> must refuse, never fabricate a causal number.
    a = answer("What is the real-world causal effect of surge on rider behavior?")
    assert a.answered is False


def test_every_tool_result_cites_a_real_file():
    for name, fn in REGISTRY.items():
        try:
            r = fn()
        except ToolUnavailable:
            pytest.skip(f"{name} artifact missing")
        path = r.artifact_id.split("#", 1)[0]
        assert Path(path).exists(), f"{name} cites a non-existent artifact {path}"
        assert r.artifact_id and r.text


def test_benchmark_hard_gates_pass():
    from ml.copilot.benchmark import main

    rc = main([])
    assert rc == 0  # returns 0 only when ungrounded_numeric == 0 and hallucinated == 0
    d = json.loads(Path("reports/v2/copilot/correctness_benchmark.json").read_text())
    assert d["hard_gates_pass"] is True
    assert d["ungrounded_numeric_answers"] == 0
    assert d["hallucinated_answers"] == 0
    assert d["refusal_accuracy"] == 1.0


def test_router_comparison_llm_beats_keyword_on_decoys():
    from ml.copilot.benchmark import main

    main([])
    d = json.loads(Path("reports/v2/copilot/correctness_benchmark.json").read_text())
    cmp = d["router_comparison"]
    # Grounding is structural -> both routers never emit an ungrounded number.
    assert cmp["keyword"]["ungrounded_numeric_answers"] == 0
    assert cmp["claude"]["ungrounded_numeric_answers"] == 0
    # But refusing the wrong/unanswerable question needs the LLM: the keyword router returns
    # real-but-wrong-question numbers (hallucinated>0) and fails the gate; the LLM router does not.
    assert cmp["keyword"]["hallucinated_answers"] > 0
    assert cmp["keyword"]["hard_gates_pass"] is False
    assert cmp["claude"]["hallucinated_answers"] == 0
    assert cmp["claude"]["hard_gates_pass"] is True
    assert cmp["claude"]["routing_accuracy"] > cmp["keyword"]["routing_accuracy"]


def test_graphrag_benchmark_relevance_gate():
    # The GraphRAG (event-graph) half: grounding + relevance beats grounding-only and no-retrieval.
    import json
    from pathlib import Path

    from ml.copilot.graphrag_scale import GRAPH, main

    if not GRAPH.exists():
        pytest.skip("event graph snapshot missing — run `make seed-graph` first")
    assert main([]) == 0  # 0 only when flat is a genuine middle (0 < flat_correct < graph_correct)
    d = json.loads(Path("reports/v2/copilot/graphrag_benchmark.json").read_text())
    a = d["answerers"]
    # No-retrieval invents; the flat baseline and GraphRAG do not hallucinate.
    assert a["no_retrieval_floor"]["hallucinated_answers"] > 0
    assert a["flat_retrieval_baseline"]["hallucinated_answers"] == 0
    assert a["graphrag"]["hallucinated_answers"] == 0
    # The flat baseline is a real, non-strawman method: it lands strictly between floor and graph.
    assert 0.0 < a["flat_retrieval_baseline"]["correct_ratio"] < a["graphrag"]["correct_ratio"]
    # Honest: this task is graph-structural (gold = graph edges), so graph is high by construction.
    assert d["caveats"]  # circularity caveat is recorded
    assert d["graph_scale"]["events"] > 100  # real dense graph, not the 2-event demo
