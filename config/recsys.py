"""Recommendation configuration (V1_Prompt §13–§14). Defaults live in config so datasets,
candidate generation, and models are reproducible from configuration (invariant 14)."""

from __future__ import annotations

from dataclasses import dataclass, field

RECSYS_CONFIG_VERSION = "recsys-v1"


@dataclass(frozen=True)
class RecsysConfig:
    # Candidate generation
    radius_km: float = 0.8  # base search radius around the query location
    radius_expand_km: float = 0.4  # step to expand when too few feasible candidates
    max_radius_km: float = 2.0
    min_candidates: int = 5  # expand radius until at least this many (if geography allows)
    max_detour_km: float = 1.5  # RETURN detour ceiling from origin->destination path

    # Synthetic query construction (§13): jitter a positive station coordinate to synthesise the
    # rider's origin, since exact user origin is not in Trip History.
    jitter_max_m: float = 150.0  # deterministic geographic jitter magnitude (metres)

    # Split
    test_fraction: float = 0.2  # chronological holdout (latest fraction); never random (§13)

    # Negatives (implicit; selected station is the only positive)
    negatives_per_positive: int = 8
    negative_kinds: tuple[str, ...] = field(
        default_factory=lambda: ("geographic", "h3_neighbor", "popularity", "random")
    )

    # Ranking
    top_k: int = 3
    eval_k: tuple[int, ...] = field(default_factory=lambda: (1, 3))

    seed: int = 42
    version: str = RECSYS_CONFIG_VERSION
