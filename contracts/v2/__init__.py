"""ShockFlow AI V2 data contracts (scaffold).

V2 is the LLM net-business-value verification release (see ``CLAUDE_V2_APPEND_REVISED.md`` and
``docs/v2/``). This package will hold the V2-specific typed contracts, layered additively on top
of the v0 (``contracts/``) and v1 (``contracts/v1/``) contracts — nothing here breaks those.

Contracts available now (V2-00):

- ``ClaimStatus`` — the 9-value honesty taxonomy: measured / offline_benchmark / simulated /
  pending_live_label / assumption / blocked_data / blocked_external / demo_fixture / research.
- ``ResultEnvelope`` — the ``run_id`` / ``artifact_id`` / ``mode`` / ``claim_status`` /
  ``freshness`` wrapper every V2 API + UI result must carry (see ``docs/v2/V2_CLAIMS_MATRIX.md``).
  It enforces the honesty rules in code (no evidence-free numbers outside demo mode, etc.).
- ``claimstate_to_status`` — backward-compat migration from the v1 ``ClaimState``.

Planned contracts (added by their owning phase, not before they are exercised):

- ``HoldoutReport`` — H3 multi-holdout metrics (V2-01).
- ``LedgerEntry`` / ``PolicyResult`` — profit / regret accounting (V2-02, V2-04).
- ``LLMValueReport`` — No-Event / Rule-Event / LLM-Event ablation, net of cost (V2-03).
"""

from __future__ import annotations

from .enums import PRODUCT_DECISION_STATUSES, ClaimStatus, claimstate_to_status
from .envelope import ResultEnvelope
from .ledger import LedgerAssumptions, PolicyLedger

__all__ = [
    "ClaimStatus",
    "LedgerAssumptions",
    "PRODUCT_DECISION_STATUSES",
    "PolicyLedger",
    "ResultEnvelope",
    "claimstate_to_status",
]
