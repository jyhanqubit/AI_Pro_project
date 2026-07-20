"""ShockFlow AI V2 data contracts (scaffold).

V2 is the LLM net-business-value verification release (see ``CLAUDE_V2_APPEND_REVISED.md`` and
``docs/v2/``). This package will hold the V2-specific typed contracts, layered additively on top
of the v0 (``contracts/``) and v1 (``contracts/v1/``) contracts — nothing here breaks those.

Planned contracts (added by their owning phase, not before they are exercised):

- ``ResultEnvelope`` — the ``run_id`` / ``artifact_id`` / ``mode`` / ``claim_status`` /
  ``freshness`` wrapper every V2 API + UI result must carry (V2-00; see
  ``docs/v2/V2_CLAIMS_MATRIX.md``).
- ``ClaimStatus`` — measured / offline_benchmark / simulated / pending_live_label / assumption /
  blocked_data / blocked_external / demo_fixture / research.
- ``HoldoutReport`` — H3 multi-holdout metrics (V2-01).
- ``LedgerEntry`` / ``PolicyResult`` — profit / regret accounting (V2-02, V2-04).
- ``LLMValueReport`` — No-Event / Rule-Event / LLM-Event ablation, net of cost (V2-03).

This module is intentionally empty of models for now: per the operating contract, contracts are
added when they are actually used by a running phase, not as speculative stubs.
"""

from __future__ import annotations

__all__: list[str] = []
