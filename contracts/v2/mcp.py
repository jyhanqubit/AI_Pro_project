"""Tool contracts for the ShockFlow MCP server (operator copilot tools). CLAUDE.md §6, §12, V2.

Every tool result carries the same provenance the HTTP API carries — ``mode``, ``cutoff`` where
the result is time-dependent, ``claim_status`` and ``freshness``, plus ``run_id`` / ``artifact_id``
when a number comes from a committed artifact — so an answer assembled from tool calls stays
traceable exactly as the dashboards are. Errors keep the API's ``{error_code, message}`` shape.

The models reuse the existing contracts where one exists (``ResultEnvelope`` for metrics,
``OperatingMode`` / ``ClaimStatus`` enums) and wrap the three endpoint-shaped dict payloads
(statistics, pricing, served forecast) without redefining their fields, so the MCP tool and the
HTTP endpoint that already serves the same data cannot drift apart.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from config.pricing_v2 import MAX_MULTIPLIER, DynamicFareConfig
from contracts.enums import OperatingMode
from contracts.v2.enums import ClaimStatus

#: Typed metric tools the copilot may ground a number in (mirrors ``ml.copilot.tools.REGISTRY``).
MetricName = Literal[
    "forecast_wape",
    "promoted_model",
    "profit_lift",
    "best_rebalancing_policy",
    "mpc_regret",
    "llm_news_value",
    "guardrail_violations",
]

TOOL_NAMES: tuple[str, ...] = (
    "get_graph_context",
    "get_operator_statistics",
    "get_metric",
    "get_model_forecast",
    "get_pricing_quotes",
)


class ToolErrorPayload(BaseModel):
    """Structured tool failure — the same shape as the API's ``ErrorResponse``."""

    error_code: str
    message: str


class ToolProvenance(BaseModel):
    """Provenance every tool result carries (the HTTP responses carry the same fields)."""

    mode: OperatingMode
    cutoff: AwareDatetime | None = None
    claim_status: ClaimStatus
    freshness: AwareDatetime
    run_id: str | None = None
    artifact_id: str | None = None
    tool: str


class GraphContextZone(BaseModel):
    zone_id: str
    forecast_delta: float


class GraphContextCard(BaseModel):
    """One as-of event with grounded evidence and the zones it moves (GraphRAG retrieval unit)."""

    event_id: str
    title: str
    type: str
    severity: float
    effect: str
    evidence: str
    zones: list[GraphContextZone]


class GraphContext(ToolProvenance):
    event_count: int
    events: list[GraphContextCard]


class OperatorStatisticsResult(ToolProvenance):
    statistics: dict[str, Any] = Field(
        description="Same payload as GET /v2/operator/statistics (as-of aggregate state)."
    )


class ModelForecastResult(ToolProvenance):
    forecast: dict[str, Any] = Field(
        description="Same payload as GET /v2/model/forecast (promoted model, next-hour zones)."
    )


class PricingRules(BaseModel):
    """Operator-controlled pricing rule overrides for a shadow quote run.

    Only the knobs an operator may legitimately move are exposed; the hard cap
    ``MAX_MULTIPLIER`` is enforced here so no override can price above the system guardrail.
    """

    base_fare: float = Field(default=1.0, gt=0.0, le=10.0, description="Base unlock fare.")
    max_multiplier: float = Field(
        default=MAX_MULTIPLIER,
        ge=1.0,
        le=MAX_MULTIPLIER,
        description=f"Hard cap on the surcharge multiplier (system guardrail {MAX_MULTIPLIER}).",
    )
    tier_thresholds: tuple[float, float, float] = Field(
        default=(0.15, 0.40, 0.70),
        description="Scarcity-score cutoffs between the four surcharge tiers, ascending in (0, 1).",
    )
    max_credit: float = Field(default=2.0, ge=0.0, le=10.0, description="Max balancing credit.")
    event_delta_norm: float = Field(
        default=5.0,
        gt=0.0,
        description="Demand delta (departures/h) that counts as full event impact.",
    )

    @model_validator(mode="after")
    def _thresholds_ascending(self) -> PricingRules:
        t = self.tier_thresholds
        if not (0.0 < t[0] < t[1] < t[2] < 1.0):
            raise ValueError("tier_thresholds must be strictly ascending and inside (0, 1)")
        return self

    def to_config(self) -> DynamicFareConfig:
        base = DynamicFareConfig()
        tiers = tuple(min(t, self.max_multiplier) for t in base.tiers)
        return dataclasses.replace(
            base,
            base_fare=self.base_fare,
            max_multiplier=self.max_multiplier,
            tiers=tiers,
            tier_thresholds=self.tier_thresholds,
            max_credit=self.max_credit,
            event_delta_norm=self.event_delta_norm,
            version=f"{base.version}+operator",
        )


class PricingQuotesResult(ToolProvenance):
    pricing: dict[str, Any] = Field(
        description="Same payload as POST /v2/pricing/quote (SIMULATED SHADOW quotes)."
    )
    operator_override: bool
    rules_applied: PricingRules | None = None
