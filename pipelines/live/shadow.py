"""Live-news shadow pipeline (V1_Prompt §11).

Replays articles as a stream of micro-batches ordered by ``available_at`` (each distinct
availability instant = one 15-min-style micro-batch). For each batch it extracts events, refreshes
only the affected zone features (reusing the V1-02 incremental refresh), and emits a **pending**
prediction per affected zone (``claim_state=pending`` — no label yet; scored later when the delayed
Trip-History label arrives). Latency is recorded from real execution. A checkpoint makes it
**restart-safe**: re-running skips already-processed batches, so no duplicates.

Offline & deterministic (fixture stream); a live collector would sit behind a flag and its failure
must never break this replay/Demo path (§11).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from contracts.article import ArticleRecord
from contracts.event import EventExtraction
from contracts.feature import FeatureSnapshot
from pipelines.features.graph_features import GraphFeatureConfig, build_graph_features
from pipelines.features.incremental import affected_zones, refresh_incremental


@dataclass
class ShadowPrediction:
    zone_id: str
    cutoff: str
    event_exposure: float  # graph event-exposure signal at this cutoff (demo-heuristic input)
    model_version: str = "demo-heuristic-v1"
    claim_state: str = "pending"  # no label yet; scored on delayed Trip-History arrival (§11)


@dataclass
class ShadowResult:
    batches_processed: int = 0
    predictions: list[ShadowPrediction] = field(default_factory=list)
    latency_ms_per_batch: list[float] = field(default_factory=list)
    resumed_from: str | None = None

    def as_dict(self) -> dict:
        lat = sorted(self.latency_ms_per_batch)
        p50 = lat[len(lat) // 2] if lat else 0.0
        p95 = lat[int(len(lat) * 0.95)] if lat else 0.0
        return {
            "batches_processed": self.batches_processed,
            "n_pending_predictions": len(self.predictions),
            "all_pending": all(p.claim_state == "pending" for p in self.predictions),
            "latency_p50_ms": round(p50, 3),
            "latency_p95_ms": round(p95, 3),
            "resumed_from": self.resumed_from,
            "predictions": [asdict(p) for p in self.predictions],
        }


def _load_checkpoint(path: Path) -> set[str]:
    if path and path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")).get("processed", []))
    return set()


def _save_checkpoint(path: Path, processed: set[str]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"processed": sorted(processed)}, indent=2), encoding="utf-8")


def _exposure(snap: FeatureSnapshot) -> float:
    f = snap.features
    return round(f.get("distance_decayed_impact", 0.0) + f.get("neighbor_zone_impact", 0.0), 4)


def run_shadow_stream(
    events: list[EventExtraction],
    articles: list[ArticleRecord],
    *,
    config: GraphFeatureConfig | None = None,
    checkpoint_path: str | Path | None = None,
    created_at: datetime | None = None,
) -> ShadowResult:
    """Process the event stream as availability-ordered micro-batches (restart-safe)."""
    cfg = config or GraphFeatureConfig()
    ckpt = Path(checkpoint_path) if checkpoint_path else None
    processed = _load_checkpoint(ckpt) if ckpt else set()

    # Micro-batches = distinct availability instants, in order.
    instants = sorted({e.available_at for e in events if e.available_at is not None})
    result = ShadowResult(resumed_from=(sorted(processed)[-1] if processed else None))

    snapshots: list[FeatureSnapshot] = []
    seen_event_ids: set[str] = set()
    for inst in instants:
        key = inst.isoformat()
        new_events = [
            e for e in events
            if e.available_at is not None
            and e.available_at <= inst
            and e.event_id not in seen_event_ids
        ]
        if key in processed:
            # Already applied in a prior run: fold in so later batches stay correct; don't re-emit.
            seen_event_ids.update(e.event_id for e in new_events)
            snapshots = build_graph_features(events, articles, forecast_cutoff=inst,
                                             config=cfg, created_at=created_at)
            continue
        if not new_events:
            continue

        t0 = time.perf_counter()
        base_zones = [s.zone_id for s in snapshots]
        affected = affected_zones(new_events, base_zones, cfg, forecast_cutoff=inst)
        snapshots = refresh_incremental(
            snapshots, events, articles, forecast_cutoff=inst,
            new_events=new_events, config=cfg, created_at=created_at,
        )
        result.latency_ms_per_batch.append((time.perf_counter() - t0) * 1000)

        seen_event_ids.update(e.event_id for e in new_events)
        for snap in snapshots:
            if snap.zone_id in affected:
                result.predictions.append(
                    ShadowPrediction(
                        zone_id=snap.zone_id, cutoff=key, event_exposure=_exposure(snap)
                    )
                )
        result.batches_processed += 1
        processed.add(key)

    if ckpt:
        _save_checkpoint(ckpt, processed)
    return result
