"""V2 controlled vocabularies. Additive to contracts/enums.py and contracts/v1/enums.py.

V2 is the LLM net-business-value verification release (``CLAUDE_V2_APPEND_REVISED.md``). It
widens the honesty vocabulary: the v1 ``ClaimState`` (5 values) could not distinguish an offline
benchmark from a live-pending label, an assumption input from a measured result, or a
data-blocked gap from an externally-blocked one. ``ClaimStatus`` below is the 9-value taxonomy
the V2 addendum mandates.

Nothing here mutates v0/v1 enums; ``claimstate_to_status`` gives a lossless-enough upgrade path
for existing v1 artifacts so no caller breaks (invariant: no breaking change without migration).
"""

from __future__ import annotations

from enum import StrEnum


class ClaimStatus(StrEnum):
    """What may honestly be claimed about a V2 result (addendum "Claims").

    - ``MEASURED``           : scored against real, arrived labels on real data.
    - ``OFFLINE_BENCHMARK``  : measured on a fixed offline benchmark set (e.g. Copilot Q-set).
    - ``SIMULATED``          : model/policy simulation; no real users; not a causal result.
    - ``PENDING_LIVE_LABEL`` : a real prediction whose delayed ground-truth label has not arrived.
    - ``ASSUMPTION``         : an input from the versioned assumption set (cost/elasticity).
    - ``BLOCKED_DATA``       : needed data not yet collected/gated; no number is fabricated.
    - ``BLOCKED_EXTERNAL``   : an external dependency is unavailable (rate-limit, missing key).
    - ``DEMO_FIXTURE``       : deterministic demo heuristic; allowed in demo mode only.
    - ``RESEARCH``           : research-only output (RL/QAOA/etc.); never feeds product surfaces.
    """

    MEASURED = "measured"
    OFFLINE_BENCHMARK = "offline_benchmark"
    SIMULATED = "simulated"
    PENDING_LIVE_LABEL = "pending_live_label"
    ASSUMPTION = "assumption"
    BLOCKED_DATA = "blocked_data"
    BLOCKED_EXTERNAL = "blocked_external"
    DEMO_FIXTURE = "demo_fixture"
    RESEARCH = "research"


#: Claim statuses that may drive a product decision in a non-demo surface. Everything else is
#: shown as pending/blocked/assumption/demo/research and must not be presented as a live result.
PRODUCT_DECISION_STATUSES: frozenset[ClaimStatus] = frozenset(
    {ClaimStatus.MEASURED, ClaimStatus.OFFLINE_BENCHMARK}
)


def claimstate_to_status(claim_state: str) -> ClaimStatus:
    """Upgrade a v1 ``ClaimState`` value to the closest V2 ``ClaimStatus`` (migration helper).

    Backward-compatibility only: v1 artifacts keep their ``ClaimState``; when they are surfaced
    through a V2 envelope this maps them without inventing precision v1 did not have.
    ``pending`` becomes ``pending_live_label`` (v1's only pending flavour was a delayed label);
    ``dry_run`` becomes ``simulated`` (dry-run experiments were never live business results).
    """
    mapping = {
        "measured": ClaimStatus.MEASURED,
        "pending": ClaimStatus.PENDING_LIVE_LABEL,
        "simulated": ClaimStatus.SIMULATED,
        "dry_run": ClaimStatus.SIMULATED,
        "research": ClaimStatus.RESEARCH,
    }
    try:
        return mapping[claim_state]
    except KeyError as exc:  # unknown v1 value → fail loudly, never silently mislabel
        raise ValueError(f"unmappable v1 ClaimState: {claim_state!r}") from exc
