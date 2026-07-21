"""The V2-06 Copilot: route an operator question to a typed tool, or refuse.

Hard rule (V2 addendum): a numeric answer is emitted ONLY when a typed tool produced it. If the
router matches no tool, the Copilot refuses ("insufficient typed evidence") rather than inventing a
number. Every answered result carries the tool's ``artifact_id`` provenance.

The router here is a deterministic intent matcher (keyword sets) standing in for the LLM's
tool-routing step; a real LLM would route the same way. Crucially, the *numbers* never come from
the router/LLM — only from the tool — so grounding is guaranteed by construction, not by trusting
the model.
"""

from __future__ import annotations

from dataclasses import dataclass

from ml.copilot.tools import REGISTRY, ToolResult, ToolUnavailable

# Intent keywords -> tool name. Ordered most-specific first; first match wins. Specific metric
# terms (WAPE) precede generic ones ("model") so "the WAPE of the promoted model" routes to the
# WAPE tool, not the model tool.
_INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("guardrail_violations", ("guardrail", "violation", "price bound", "pricing safe")),
    ("llm_news_value", ("llm", "news event", "news-derived", "gpt", "claude value")),
    ("mpc_regret", ("regret", "oracle", "optimality gap", "close to optimal")),
    ("best_rebalancing_policy", ("best policy", "which policy", "rebalanc", "mpc or", "policy to use")),
    ("forecast_wape", ("wape", "forecast error", "forecast accuracy", "holdout", "how accurate")),
    ("profit_lift", ("profit", "worth", "beat", "dollar", "money", "revenue lift", "net gain")),
    ("promoted_model", ("which model", "promoted model", "served model", "what model", "algorithm")),
]


@dataclass(frozen=True)
class CopilotAnswer:
    question: str
    answered: bool
    tool: str | None
    text: str
    value: object | None
    artifact_id: str | None
    claim_status: str | None
    refusal_reason: str | None = None

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.value, (int, float))


_REFUSAL = "Insufficient typed evidence: no tool can ground this — I won't guess a number."


def route(question: str) -> str | None:
    q = question.lower()
    for tool, kws in _INTENTS:
        if any(k in q for k in kws):
            return tool
    return None


def answer(question: str, route_fn=route) -> CopilotAnswer:
    """Answer a question. ``route_fn`` selects the tool (or None to refuse); defaults to the
    deterministic keyword router. Inject a different router (e.g. real-LLM routing) to compare."""
    tool_name = route_fn(question)
    if tool_name is None:
        return CopilotAnswer(question, False, None, _REFUSAL, None, None, None,
                             refusal_reason="no_tool_match")
    try:
        res: ToolResult = REGISTRY[tool_name]()
    except ToolUnavailable as exc:
        return CopilotAnswer(question, False, tool_name,
                             f"Tool '{tool_name}' unavailable: {exc}", None, None, None,
                             refusal_reason="tool_unavailable")
    return CopilotAnswer(question, True, tool_name, res.text, res.value, res.artifact_id,
                         res.claim_status)
