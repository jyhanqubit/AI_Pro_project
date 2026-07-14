"""Deterministic zone clustering + switchback assignment (V1_Prompt §17).

Zones are clustered deterministically; each cluster switches arm across time blocks with a
seeded phase, so treatment/control are balanced within a cluster over time (the switchback design).
Same seed + inputs -> same assignment (invariant 14). Assignment is balanced by construction, so the
known propensity is 0.5.
"""

from __future__ import annotations

import hashlib


def _stable_int(key: str) -> int:
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def cluster_zones(zones: list[str], n_clusters: int, seed: int = 42) -> dict[str, str]:
    """Assign each zone to a cluster deterministically (hash-based, stable ordering)."""
    n = max(1, n_clusters)
    out: dict[str, str] = {}
    for z in sorted(set(zones)):
        c = _stable_int(f"{seed}:{z}") % n
        out[z] = f"cluster_{c}"
    return out


def switchback_assignment(
    cluster_ids: list[str], n_time_blocks: int, arms: tuple[str, str], seed: int = 42
) -> dict[tuple[str, int], str]:
    """(cluster, time_block) -> arm. Each cluster alternates arms; **starting phases are balanced**
    across clusters so that, within every time block, the arms are split evenly. This removes the
    temporal confound that would otherwise bias an A/A test (equal arms → ~0 effect)."""
    clusters = sorted(set(cluster_ids))
    assign: dict[tuple[str, int], str] = {}
    for i, c in enumerate(clusters):
        phase = i % len(arms)  # balanced phases (not seeded) -> per-block arm balance
        for t in range(n_time_blocks):
            assign[(c, t)] = arms[(t + phase) % len(arms)]
    return assign


def assignment_shares(
    assignment: dict[tuple[str, int], str], arms: tuple[str, str]
) -> dict[str, float]:
    """Observed share of units in each arm (for the SRM check)."""
    total = len(assignment) or 1
    counts = {a: 0 for a in arms}
    for arm in assignment.values():
        counts[arm] = counts.get(arm, 0) + 1
    return {a: counts[a] / total for a in arms}
