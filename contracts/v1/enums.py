"""V1 controlled vocabularies. Additive to contracts/enums.py (V1_Prompt §6).

The v0 ``OperatingMode`` (contracts/enums.py) stays authoritative for v0 records. V1 adds three
serving/analysis modes on top of the v0 four, and a ``ClaimState`` that pins every predicted
artifact to what can honestly be claimed about it.
"""

from __future__ import annotations

from enum import StrEnum


class OperatingModeV1(StrEnum):
    """Six V1 operating modes (V1_Prompt §6). Superset of the v0 four.

    The first four match ``contracts.enums.OperatingMode`` value-for-value so a v0 mode string
    parses unchanged. ``LIVE_SHADOW`` runs live collection/inference without acting on it;
    ``POLICY_SIMULATION`` and ``EXPERIMENT_DRY_RUN`` never emit measured business results.
    """

    DEMO_FIXTURE = "demo_fixture"
    HISTORICAL_REPLAY = "historical_replay"
    LIVE_SHADOW = "live_shadow"
    POLICY_SIMULATION = "policy_simulation"
    EXPERIMENT_DRY_RUN = "experiment_dry_run"
    RESEARCH = "research"


class ClaimState(StrEnum):
    """What may be claimed about a predicted/serving artifact (V1_Prompt §4 invariants 6, 7, 10).

    - ``MEASURED``     : scored against a real, arrived label.
    - ``PENDING``      : a real prediction whose label has not arrived yet (``pending_label``).
    - ``SIMULATED``    : produced by a choice/policy simulator; NOT a live business result.
    - ``DRY_RUN``      : experiment plumbing exercised without real exposure.
    - ``RESEARCH``     : research-only output (e.g. QUBO/QAOA); never fed to serving views.
    """

    MEASURED = "measured"
    PENDING = "pending"
    SIMULATED = "simulated"
    DRY_RUN = "dry_run"
    RESEARCH = "research"


class RecommendationMode(StrEnum):
    """Context-aware station recommendation direction (V1_Prompt §13). Not personalised CF."""

    RENT = "rent"
    RETURN = "return"


class AnomalyType(StrEnum):
    """Anomaly detector families (V1_Prompt §12)."""

    DATA_QUALITY = "data_quality"
    INVENTORY = "inventory"
    FORECAST_RESIDUAL = "forecast_residual"
    PROXY_DEMAND = "proxy_demand"


class RootCauseStatus(StrEnum):
    """Root-cause attribution for an anomaly (V1_Prompt §12)."""

    EXPLAINED_BY_EVENT = "explained_by_event"
    PARTIALLY_EXPLAINED = "partially_explained"
    UNEXPLAINED = "unexplained"
    LIKELY_DATA_QUALITY = "likely_data_quality"
    INVENTORY_DISLOCATION = "inventory_dislocation"


class ReasonCode(StrEnum):
    """Recommendation explanation codes — reason codes, never attention weights (V1_Prompt §15)."""

    HIGH_SUCCESS_PROBABILITY = "HIGH_SUCCESS_PROBABILITY"
    LOW_DETOUR = "LOW_DETOUR"
    LOW_SHORTAGE_RISK = "LOW_SHORTAGE_RISK"
    LOW_OVERFLOW_RISK = "LOW_OVERFLOW_RISK"
    EVENT_IMPACT_AVOIDED = "EVENT_IMPACT_AVOIDED"
    NETWORK_BALANCE_BENEFIT = "NETWORK_BALANCE_BENEFIT"
    INVENTORY_STALE = "INVENTORY_STALE"
