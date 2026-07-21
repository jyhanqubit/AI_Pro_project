"""Typed tools for the V2-06 Copilot — each reads a committed V2 artifact and returns a grounded,
provenance-carrying result. The Copilot may only surface a number that came from one of these.

Every tool returns a ``ToolResult`` whose ``artifact_id`` points at the exact file (+ JSON path)
the value came from, so any surfaced number is traceable to a real measured/simulated artifact.
A tool raises ``ToolUnavailable`` when its backing artifact is missing (run the owning phase).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_R = Path("reports/v2")


class ToolUnavailable(RuntimeError):
    """The backing artifact is missing — the owning phase must be run first."""


@dataclass(frozen=True)
class ToolResult:
    name: str
    value: Any
    unit: str
    artifact_id: str
    claim_status: str
    text: str  # a one-line grounded phrasing


def _load(path: Path) -> dict:
    if not path.exists():
        raise ToolUnavailable(f"{path} missing — run its owning make target first.")
    return json.loads(path.read_text(encoding="utf-8"))


def forecast_wape() -> ToolResult:
    d = _load(_R / "holdout" / "h3_multiholdout.json")
    v = d["aggregate"]["wape"]["mean"]
    return ToolResult("forecast_wape", round(v, 4), "WAPE",
                      "reports/v2/holdout/h3_multiholdout.json#aggregate.wape.mean",
                      d.get("claim_status", "measured"),
                      f"The promoted model's aggregate H3 multi-holdout WAPE is {v:.4f} (measured).")


def promoted_model() -> ToolResult:
    d = _load(_R / "holdout" / "promoted_model.json")
    algo = d["algorithm"]
    return ToolResult("promoted_model", algo, "algorithm",
                      "reports/v2/holdout/promoted_model.json#algorithm",
                      d.get("claim_status", "measured"),
                      f"The promoted (served) model is {algo}.")


def profit_lift() -> ToolResult:
    d = _load(_R / "ledger" / "profit_regret.json")
    v = d["predictive_lift_to_profit"]["model_minus_no_action_net"]
    return ToolResult("profit_lift", round(v, 2), "USD (simulated)",
                      "reports/v2/ledger/profit_regret.json#predictive_lift_to_profit.model_minus_no_action_net",
                      d.get("claim_status", "simulated"),
                      f"The promoted forecast nets ${v:,.0f} more than the seasonal-naive baseline "
                      f"(simulated, assumption-conditioned).")


def best_rebalancing_policy() -> ToolResult:
    d = _load(_R / "mpc" / "policy_comparison.json")
    ranking = [p for p in d["ranking_by_total_cost"] if p != "oracle"]
    best = ranking[0]
    return ToolResult("best_rebalancing_policy", best, "policy",
                      "reports/v2/mpc/policy_comparison.json#ranking_by_total_cost",
                      d.get("claim_status", "simulated"),
                      f"The best feasible rebalancing policy is {best} (Oracle is an offline bound, "
                      f"excluded).")


def mpc_regret() -> ToolResult:
    d = _load(_R / "mpc" / "policy_comparison.json")
    v = d["by_policy"]["mpc"]["regret_vs_oracle"]
    return ToolResult("mpc_regret", round(v, 1), "ledger cost (simulated)",
                      "reports/v2/mpc/policy_comparison.json#by_policy.mpc.regret_vs_oracle",
                      d.get("claim_status", "simulated"),
                      f"MPC's regret vs the perfect-foresight Oracle is {v:.1f} (simulated).")


def llm_news_value() -> ToolResult:
    d = _load(_R / "llm_value" / "incremental_value_borough.json")
    v = d["net_llm_value_simulated"]
    return ToolResult("llm_news_value", round(v, 2), "USD (simulated)",
                      "reports/v2/llm_value/incremental_value_borough.json#net_llm_value_simulated",
                      d.get("claim_status", "measured"),
                      f"The LLM-from-news event layer's net value is ${v:,.0f} — negative; it does "
                      f"not beat the structured event feed on this data.")


def guardrail_violations() -> ToolResult:
    d = _load(_R / "pricing" / "guardrail_audit.json")
    v = d["violation_count"]
    return ToolResult("guardrail_violations", int(v), "count",
                      "reports/v2/pricing/guardrail_audit.json#violation_count",
                      d.get("claim_status", "simulated"),
                      f"The dynamic-pricing policy had {v} guardrail violations.")


#: Registry: tool name -> callable. The router picks one of these; anything outside is refused.
REGISTRY = {
    "forecast_wape": forecast_wape,
    "promoted_model": promoted_model,
    "profit_lift": profit_lift,
    "best_rebalancing_policy": best_rebalancing_policy,
    "mpc_regret": mpc_regret,
    "llm_news_value": llm_news_value,
    "guardrail_violations": guardrail_violations,
}
