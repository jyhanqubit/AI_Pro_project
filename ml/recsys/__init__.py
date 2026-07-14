"""Context-aware station recommendation (V1_Prompt §13–§15).

RENT/RETURN station ranking — NOT personalised collaborative filtering. The dataset uses the
actual chosen station from Trip History as the positive; unchosen candidates are implicit
negatives; the rider's exact origin is unknown, so a query is synthesised by deterministic
geographic jitter of the positive station and flagged ``query_is_synthetic=true``.

Offline & deterministic: same input + config + seed → same dataset (invariant 14). No selected
station id ever enters the query features (leakage guard, §13 acceptance).
"""

from __future__ import annotations

from .candidates import Candidate, generate_candidates
from .dataset import RecSample, build_dataset, chronological_split
from .stations import StationMaster, build_station_master

__all__ = [
    "StationMaster",
    "build_station_master",
    "RecSample",
    "build_dataset",
    "chronological_split",
    "Candidate",
    "generate_candidates",
]
