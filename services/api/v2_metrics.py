"""V2-07 — artifact-backed cockpit metrics.

The V2-07 contract: **every metric a surface shows resolves to a committed `reports/v2/**`
artifact** — no hard-coded numbers. This module is the single source for the operator cockpit's
headline metrics. Each metric's value is read live from its artifact (via the already-artifact-backed
copilot tools) and wrapped in a ``ResultEnvelope`` that carries ``run_id`` / ``artifact_id`` /
``mode`` / ``claim_status`` / ``freshness`` and enforces the honesty rules (e.g. a ``research`` result
can never appear on a product surface; a measured value in a non-demo mode must cite an artifact).

If an artifact is missing, that metric surfaces as a blocked envelope (``value=None``) rather than a
fabricated number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.enums import OperatingMode
from contracts.v2.enums import ClaimStatus
from contracts.v2.envelope import ResultEnvelope
from ml.copilot.tools import REGISTRY, ToolUnavailable

# cockpit metric key -> (human label, copilot tool name that reads its artifact)
_METRICS: list[tuple[str, str, str]] = [
    ("forecast_wape", "H3 multi-holdout WAPE", "forecast_wape"),
    ("promoted_model", "Served model", "promoted_model"),
    ("profit_lift", "Forecast profit vs no-action", "profit_lift"),
    ("best_policy", "Best rebalancing policy", "best_rebalancing_policy"),
    ("mpc_regret", "MPC regret vs Oracle", "mpc_regret"),
    ("guardrail_violations", "Pricing guardrail violations", "guardrail_violations"),
    ("llm_news_value", "LLM-from-news net value", "llm_news_value"),
]


def _artifact_meta(artifact_id: str) -> tuple[str, str | None]:
    """Read run_id + freshness from the artifact file the metric points at."""
    path = Path(artifact_id.split("#", 1)[0])
    if not path.exists():
        return "unknown", None
    d = json.loads(path.read_text(encoding="utf-8"))
    return str(d.get("run_id", "unknown")), d.get("freshness")


def cockpit_metrics(mode: OperatingMode = OperatingMode.HISTORICAL_REPLAY) -> list[dict[str, Any]]:
    """Every headline cockpit metric, each resolved from its committed artifact and enveloped.

    A ``research``-status metric is never emitted on a non-research surface (the envelope would
    reject it); a missing artifact yields a blocked envelope with ``value=None``.
    """
    out: list[dict[str, Any]] = []
    for key, label, tool in _METRICS:
        try:
            res = REGISTRY[tool]()
            run_id, freshness = _artifact_meta(res.artifact_id)
            claim = ClaimStatus(res.claim_status)
            if claim == ClaimStatus.RESEARCH and mode != OperatingMode.RESEARCH:
                continue  # research never feeds product surfaces
            env = ResultEnvelope(
                value=res.value, run_id=run_id, artifact_id=res.artifact_id,
                mode=mode, claim_status=claim,
                freshness=freshness or "1970-01-01T00:00:00+00:00",
            )
            out.append({"key": key, "label": label, "unit": res.unit,
                        "text": res.text, "envelope": env.model_dump(mode="json")})
        except (ToolUnavailable, FileNotFoundError, KeyError, ValueError) as exc:
            # blocked/pending — surface the absence, never a fabricated number
            out.append({"key": key, "label": label, "unit": None, "text": f"unavailable: {exc}",
                        "envelope": ResultEnvelope(
                            value=None, run_id="unknown", artifact_id=None, mode=mode,
                            claim_status=ClaimStatus.BLOCKED_DATA,
                            freshness="1970-01-01T00:00:00+00:00").model_dump(mode="json")})
    return out
