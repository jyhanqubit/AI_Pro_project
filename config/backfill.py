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
    "path",
    "transit",
    "subway",
    "signal",
    "delay",
    "suspend",
    "closure",
    "road",
    "concert",
    "venue",
    "event",
    "game",
    "festival",
    "parade",
    "weather",
    "storm",
    "flood",
    "accident",
    "gathering",
    "protest",
    "march",
)

# City/region filter — only articles mentioning the served area are kept. Anchored on unambiguous
# Hudson-County place names (bare "Newport"/"Grove"/"PATH" are too generic → false positives).
DEFAULT_CITY_TERMS: tuple[str, ...] = (
    "hoboken",
    "jersey city",
    "journal square",
    "grove street",
    "hudson county",
    "exchange place",
    "newport pkwy",
    "jersey city city hall",
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


# Default GDELT DOC query for the served area's **bike-demand-relevant** news (opt-in live
# collection). Anchored on Jersey City / Hoboken, and targeted at what actually shifts bike-share
# demand: the bike system itself, plus the mobility disruptions and crowd-draws that push riders
# onto bikes. Broad words are excluded to keep the signal-to-noise usable.
DEFAULT_GDELT_QUERY = (
    '("Jersey City" OR Hoboken OR "Journal Square" OR "Hudson County") '
    '("Citi Bike" OR CitiBike OR "bike share" OR "bike lane" OR bicycle OR cycling OR '
    'e-bike OR "NJ Transit" OR PATH train OR "light rail" OR commute OR "road closure" OR '
    'detour OR "street closure" OR concert OR festival OR flood)'
)

# NYC preset for a real backfill over the Citi Bike core service area (Manhattan / Brooklyn /
# Queens / Bronx). Pair with an NYC trip window (--start/--end) and the NYC gazetteer in
# config/places.py so extracted events geocode onto zones that carry trip demand. `--region nyc`.
NYC_GDELT_QUERY = (
    '("New York City" OR Manhattan OR Brooklyn OR Queens OR "Times Square" OR '
    '"Union Square" OR "Penn Station" OR "Grand Central" OR "Madison Square Garden" OR '
    '"Barclays Center" OR Williamsburg OR Harlem) '
    '("Citi Bike" OR CitiBike OR "bike share" OR "bike lane" OR bicycle OR cycling OR '
    'e-bike OR subway OR MTA OR "service change" OR "signal problem" OR "road closure" OR '
    'detour OR "street closure" OR concert OR festival OR parade OR marathon OR flood OR storm)'
)

# Region presets selectable on the live collector (`--region`). A `--query` override always wins.
GDELT_QUERY_PRESETS: dict[str, str] = {"jc": DEFAULT_GDELT_QUERY, "nyc": NYC_GDELT_QUERY}


# Guardian Content API query presets (§7.4). Guardian's query syntax uses AND/OR/quotes; anchor on
# the served area AND a mobility/crowd term so results are demand-relevant. `--source guardian`.
GUARDIAN_JC_QUERY = (
    '("Jersey City" OR Hoboken OR "Journal Square" OR "Hudson County") '
    'AND ("bike share" OR "Citi Bike" OR "bike lane" OR cycling OR "NJ Transit" OR PATH OR '
    '"light rail" OR commute OR "road closure" OR detour OR concert OR festival OR flood)'
)
GUARDIAN_NYC_QUERY = (
    '("New York City" OR Manhattan OR Brooklyn OR Queens OR "Times Square" OR '
    '"Madison Square Garden" OR "Penn Station") '
    'AND ("bike share" OR "Citi Bike" OR "bike lane" OR cycling OR subway OR MTA OR '
    '"service change" OR "road closure" OR detour OR concert OR festival OR parade OR '
    'marathon OR flood OR storm)'
)
GUARDIAN_QUERY_PRESETS: dict[str, str] = {"jc": GUARDIAN_JC_QUERY, "nyc": GUARDIAN_NYC_QUERY}


@dataclass(frozen=True)
class GdeltConfig:
    query: str = DEFAULT_GDELT_QUERY
    source_lang: str = "english"
    max_records: int = 75
    start: str | None = None  # "YYYYMMDDHHMMSS" UTC; None = GDELT default recent window
    end: str | None = None
    enabled: bool = False  # opt-in; live network. Never on in Demo/tests.
