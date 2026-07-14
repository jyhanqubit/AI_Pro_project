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

# City/region filter — only articles mentioning the served area are kept. Anchored on unambiguous
# Hudson-County place names (bare "Newport"/"Grove"/"PATH" are too generic → false positives).
DEFAULT_CITY_TERMS: tuple[str, ...] = (
    "hoboken", "jersey city", "journal square", "grove street", "hudson county",
    "exchange place", "newport pkwy", "jersey city city hall",
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


# Default GDELT DOC query for the served area's mobility-relevant news (opt-in live collection).
# Strong Jersey City / Hoboken anchor AND mobility-specific terms only — broad words like
# "event/storm/train" pull in national noise, so they are deliberately excluded.
DEFAULT_GDELT_QUERY = (
    '("Jersey City" OR Hoboken OR "Journal Square") '
    '("NJ Transit" OR PATH train OR "light rail" OR commute OR "road closure" OR '
    'detour OR "street closure" OR "service change" OR "station closed")'
)


@dataclass(frozen=True)
class GdeltConfig:
    query: str = DEFAULT_GDELT_QUERY
    source_lang: str = "english"
    max_records: int = 75
    start: str | None = None  # "YYYYMMDDHHMMSS" UTC; None = GDELT default recent window
    end: str | None = None
    enabled: bool = False  # opt-in; live network. Never on in Demo/tests.
