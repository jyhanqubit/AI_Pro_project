"""The V2 result envelope.

Every V2 API response and UI metric must be traceable to an artifact and honestly labeled
(``CLAUDE_V2_APPEND_REVISED.md`` → "Claims", "Productization"; ``docs/v2/V2_CLAIMS_MATRIX.md``).
``ResultEnvelope`` is the wrapper that carries that contract on every surfaced value:

    run_id · artifact_id · mode · claim_status · freshness (+ the value itself)

The model enforces the honesty rules that the docs state in prose, so a mislabeled or
evidence-free result fails validation instead of reaching a reviewer:

- A product-decision value (``measured`` / ``offline_benchmark``) surfaced in a non-demo mode
  must cite an ``artifact_id`` — no evidence-free numbers in live/replay/research views.
- ``demo_fixture`` results may appear only in demo mode.
- ``research`` results may appear only in research mode (research never feeds product surfaces).
- ``freshness`` is timezone-aware (base-contract §5.1).
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import AwareDatetime, Field, model_validator

from contracts.common import ContractModel
from contracts.enums import OperatingMode

from .enums import PRODUCT_DECISION_STATUSES, ClaimStatus

T = TypeVar("T")


class ResultEnvelope(ContractModel, Generic[T]):
    """Traceable, honestly-labeled wrapper around a single surfaced V2 result.

    ``value`` is optional so an envelope can represent a blocked/pending result (value ``None``)
    without fabricating a number — the ``claim_status`` then explains why it is absent.
    """

    value: T | None = Field(
        default=None,
        description="The surfaced result; None when blocked/pending (see claim_status).",
    )
    run_id: str = Field(
        min_length=1,
        description="Identifier of the execution that produced this result (e.g. 'run_...').",
    )
    artifact_id: str | None = Field(
        default=None,
        description="Where the value is persisted, e.g. 'reports/v2/holdout/h3_multiholdout.json#aggregate.wape'.",
    )
    mode: OperatingMode = Field(
        description="Operating mode of the surface this result is shown on.",
    )
    claim_status: ClaimStatus = Field(
        description="What may honestly be claimed about the value.",
    )
    freshness: AwareDatetime = Field(
        description="When the backing artifact was produced (timezone-aware).",
    )

    @property
    def is_product_decisionable(self) -> bool:
        """True when the value may drive a product decision on a non-demo surface."""
        return self.claim_status in PRODUCT_DECISION_STATUSES

    @model_validator(mode="after")
    def _enforce_honesty_rules(self) -> ResultEnvelope[T]:
        # 1. Evidence rule: a decisionable value shown outside demo mode must cite an artifact.
        if (
            self.value is not None
            and self.mode is not OperatingMode.DEMO_FIXTURE
            and self.claim_status in PRODUCT_DECISION_STATUSES
            and not self.artifact_id
        ):
            raise ValueError(
                f"{self.claim_status} value in mode={self.mode} requires an artifact_id "
                "(no evidence-free numbers outside demo mode)"
            )
        # 2. demo_fixture results only in demo mode.
        if self.claim_status is ClaimStatus.DEMO_FIXTURE and self.mode is not OperatingMode.DEMO_FIXTURE:
            raise ValueError("claim_status=demo_fixture is allowed only in mode=demo_fixture")
        # 3. research results only in research mode (research never feeds product surfaces).
        if self.claim_status is ClaimStatus.RESEARCH and self.mode is not OperatingMode.RESEARCH:
            raise ValueError("claim_status=research is allowed only in mode=research")
        # 4. A blocked/pending status must not carry a fabricated value.
        blocked_or_pending = {
            ClaimStatus.BLOCKED_DATA,
            ClaimStatus.BLOCKED_EXTERNAL,
            ClaimStatus.PENDING_LIVE_LABEL,
        }
        if self.claim_status in blocked_or_pending and self.value is not None:
            raise ValueError(
                f"claim_status={self.claim_status} must not carry a value "
                "(blocked/pending results are shown without a number)"
            )
        return self
