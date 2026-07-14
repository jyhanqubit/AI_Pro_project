"""Historical news backfill & coverage-gate configuration (V1_Prompt §7).

Real GDELT live fetch is disabled by default (offline Demo). The deterministic fixture provider is
the default source; the coverage gate is set to sensible thresholds for the demo fixture scale. No
timestamps are shifted and no news is fabricated (§7 gate-failure rules).
"""

from __future__ import annotations

from dataclasses import dataclass, field

BACKFILL_CONFIG_VERSION = "backfill-v1"

# Ontology keywords that mark an article as a demand-relevant candidate (case-insensitive).
DEFAULT_ONTOLOGY_TERMS: tuple[str, ...] = (
    "path", "transit", "subway", "signal", "delay", "suspend", "closure", "road",
    "concert", "venue", "event", "game", "festival", "parade", "weather", "storm",
    "flood", "accident", "gathering", "protest", "march",
)

# City/region filter — only articles mentioning the served area are kept.
DEFAULT_CITY_TERMS: tuple[str, ...] = (
    "hoboken", "jersey city", "grove", "newport", "exchange place", "city hall",
    "journal square", "waterfront", "path",
)


@dataclass(frozen=True)
class BackfillConfig:
    ontology_terms: tuple[str, ...] = DEFAULT_ONTOLOGY_TERMS
    city_terms: tuple[str, ...] = DEFAULT_CITY_TERMS
    require_city_match: bool = True
    require_ontology_match: bool = True

    # Coverage gate thresholds (demo scale; raise for real backfills).
    min_accepted_articles: int = 1
    min_unique_sources: int = 1
    min_ontology_match_ratio: float = 0.25  # of raw -> candidate

    checkpoint_dir: str = "data/processed/backfill"
    seed: int = 42
    version: str = BACKFILL_CONFIG_VERSION
    _extra: tuple[str, ...] = field(default_factory=tuple)
