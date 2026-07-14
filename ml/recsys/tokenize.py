"""Tokenise RecSample / Station into ShockFlowRecFormerRetriever tensors (V1_Prompt §14).

Builds the per-token feature tensors + presence/padding masks the towers consume. Optional feature
groups (forecast, inventory) and EVENT tokens are absent by default on plain Trip History; their
masks make that explicit so the model never sees fabricated values (invariant 6).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import torch
from torch import Tensor

from config.recsys import RetrieverConfig
from contracts.v1.enums import RecommendationMode
from pipelines.features.zones import zone_for

from .dataset import RecSample
from .encoder import EVENT_FEAT_DIM, RECENCY_BUCKETS
from .stations import Station, StationMaster

# JC / Hoboken reference centre for geo normalisation.
_CENTER_LAT, _CENTER_LNG = 40.725, -74.040

# Optional per-item context providers (default: none -> masked).
# ForecastProvider: zone_id -> (baseline, event_aware, delta) | None
ForecastProvider = Callable[[str], "tuple[float, float, float] | None"]
# EventProvider: zone_id -> [(severity, confidence, signed_direction, recency_bucket), ...]
EventProvider = Callable[[str], list[tuple[float, float, float, float]]]


def _geo(lat: float, lng: float) -> list[float]:
    return [(lat - _CENTER_LAT) * 100.0, (lng - _CENTER_LNG) * 100.0]


def _time(hour: int, dow: int) -> list[float]:
    return [
        math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24),
        math.sin(2 * math.pi * dow / 7), math.cos(2 * math.pi * dow / 7),
    ]


class RetrieverTokenizer:
    def __init__(self, master: StationMaster, cfg: RetrieverConfig) -> None:
        self.master = master
        self.cfg = cfg
        self._vocab = {sid: i for i, sid in enumerate(master.ids())}
        self.num_stations = len(self._vocab)

    def station_index(self, station_id: str) -> int:
        """Vocab index; OOV bucket (== num_stations) for cold-start/unseen stations."""
        return self._vocab.get(station_id, self.num_stations)

    # --- events ---------------------------------------------------------------------------------
    def _events(
        self, zone_ids: Sequence[str], provider: EventProvider | None, device: torch.device
    ) -> tuple[Tensor, Tensor, Tensor]:
        rows = [list(provider(z)) if provider else [] for z in zone_ids]
        e = max(1, min(self.cfg.max_event_tokens, max((len(r) for r in rows), default=0)))
        b = len(zone_ids)
        feats = torch.zeros(b, e, EVENT_FEAT_DIM)
        present = torch.zeros(b, e, dtype=torch.bool)
        recency = torch.zeros(b, e, dtype=torch.long)
        for i, r in enumerate(rows):
            for j, (sev, conf, direction, rec) in enumerate(r[:e]):
                feats[i, j] = torch.tensor([sev, conf, direction, rec])
                present[i, j] = True
                recency[i, j] = min(RECENCY_BUCKETS - 1, max(0, int(rec)))
        return feats.to(device), present.to(device), recency.to(device)

    # --- query ----------------------------------------------------------------------------------
    def query_batch(
        self,
        samples: Sequence[RecSample],
        forecast: ForecastProvider | None = None,
        events: EventProvider | None = None,
        device: torch.device | None = None,
    ) -> dict[str, object]:
        dev = device or torch.device("cpu")
        mode = torch.tensor(
            [0 if s.mode == RecommendationMode.RENT else 1 for s in samples], dtype=torch.long
        )
        geo = torch.tensor([_geo(s.query_lat, s.query_lng) for s in samples], dtype=torch.float)
        time = torch.tensor([_time(s.hour, s.dow) for s in samples], dtype=torch.float)
        constraint = torch.tensor(
            [[float(s.is_member), self.cfg_detour(s), self.cfg_radius()] for s in samples],
            dtype=torch.float,
        )
        # Context is keyed on the QUERY LOCATION's zone, never the chosen station (leakage guard).
        query_zones = [zone_for(s.query_lat, s.query_lng) for s in samples]
        fc, fc_present = self._forecast(query_zones, forecast)
        inv = torch.zeros(len(samples), 3)  # LOCAL_INVENTORY absent by default
        inv_present = torch.zeros(len(samples), dtype=torch.bool)
        ev_feats, ev_present, ev_rec = self._events(query_zones, events, dev)
        return {
            "scalar_feats": {
                "MODE": mode.to(dev), "GEO": geo.to(dev), "TIME": time.to(dev),
                "CONSTRAINT": constraint.to(dev), "FORECAST": fc.to(dev),
                "LOCAL_INVENTORY": inv.to(dev),
            },
            "scalar_present": {
                "FORECAST": fc_present.to(dev),
                "LOCAL_INVENTORY": inv_present.to(dev),
            },
            "event_feats": ev_feats, "event_present": ev_present, "event_recency": ev_rec,
        }

    def cfg_detour(self, s: RecSample) -> float:
        return 1.0

    def cfg_radius(self) -> float:
        return 1.0

    # --- stations -------------------------------------------------------------------------------
    def station_batch(
        self,
        stations: Sequence[Station],
        forecast: ForecastProvider | None = None,
        events: EventProvider | None = None,
        device: torch.device | None = None,
    ) -> dict[str, object]:
        dev = device or torch.device("cpu")
        static = torch.tensor(
            [self.station_index(st.station_id) for st in stations], dtype=torch.long
        )
        geo = torch.tensor([_geo(st.lat, st.lng) for st in stations], dtype=torch.float)
        inv = torch.tensor(
            [[float(st.bikes_available or 0), float(st.docks_available or 0),
              float(st.capacity or 0)] for st in stations], dtype=torch.float
        )
        inv_present = torch.tensor([st.inventory_known for st in stations], dtype=torch.bool)
        op = torch.tensor(
            [[float(st.is_renting), float(st.is_returning),
              float((st.bikes_available or 0) - (st.docks_available or 0))] for st in stations],
            dtype=torch.float,
        )
        fc, fc_present = self._forecast_stations(stations, forecast)
        ev_feats, ev_present, ev_rec = self._events([st.zone_id for st in stations], events, dev)
        return {
            "scalar_feats": {
                "STATION_STATIC": static.to(dev), "STATION_GEO": geo.to(dev),
                "INVENTORY": inv.to(dev), "FORECAST": fc.to(dev), "OPERATION": op.to(dev),
            },
            "scalar_present": {"INVENTORY": inv_present.to(dev), "FORECAST": fc_present.to(dev)},
            "event_feats": ev_feats, "event_present": ev_present, "event_recency": ev_rec,
        }

    def _forecast(
        self, zone_ids: Sequence[str], provider: ForecastProvider | None
    ) -> tuple[Tensor, Tensor]:
        n = len(zone_ids)
        feats = torch.zeros(n, 3)
        present = torch.zeros(n, dtype=torch.bool)
        if provider is None:
            return feats, present
        for i, z in enumerate(zone_ids):
            got = provider(z)
            if got is not None:
                feats[i] = torch.tensor(got)
                present[i] = True
        return feats, present

    def _forecast_stations(
        self, stations: Sequence[Station], provider: ForecastProvider | None
    ) -> tuple[Tensor, Tensor]:
        n = len(stations)
        feats = torch.zeros(n, 3)
        present = torch.zeros(n, dtype=torch.bool)
        if provider is None:
            return feats, present
        for i, st in enumerate(stations):
            got = provider(st.zone_id)
            if got is not None:
                feats[i] = torch.tensor(got)
                present[i] = True
        return feats, present
