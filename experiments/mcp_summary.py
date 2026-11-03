"""Compact ("summary") variants of the MCP copilot tool payloads, plus answer-preservation checks.

The existing five tools (``services/mcp/server.py``) return the full payloads the dashboards use.
A summary keeps the provenance block, the aggregates and the top-N rows with only the fields a
question needs, and points at the full result (``full_result_ref``) instead of inlining it.

Each ``check_*`` function derives the answer to the scenario question from the raw payload and
from the summary and asserts they agree; it returns a one-line statement for the report.
"""

from __future__ import annotations

from typing import Any

PROVENANCE_FIELDS = ("tool", "mode", "cutoff", "claim_status", "freshness", "run_id", "artifact_id")


def _provenance(raw: dict[str, Any]) -> dict[str, Any]:
    return {k: raw.get(k) for k in PROVENANCE_FIELDS}


def _ref(raw: dict[str, Any], tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """How to get the full payload back: the tool call, and the artifact/run it came from."""
    return {
        "tool": tool,
        "args": args,
        "run_id": raw.get("run_id"),
        "artifact_id": raw.get("artifact_id"),
    }


# --- scenario A: next-hour forecast for specific zones ----------------------------------------


def summarize_model_forecast(
    raw: dict[str, Any], *, zone_ids: list[str] | None = None, top_n: int = 5
) -> dict[str, Any]:
    """Keep model identity, the aggregate over every served zone, and only the asked rows."""
    f = raw["forecast"]
    rows = list(f.get("forecasts", []))
    if zone_ids:
        wanted = set(zone_ids)
        kept = [r for r in rows if r["zone_id"] in wanted]
    else:
        kept = rows[:top_n]
    values = [float(r["predicted_departures"]) for r in rows]
    model = f.get("model", {})
    return {
        **_provenance(raw),
        "summary_of": "get_model_forecast",
        "serving_hour": f.get("serving_hour"),
        "forecast_horizon_h": f.get("forecast_horizon_h"),
        "model": {
            "algorithm": model.get("algorithm"),
            "feature_version": model.get("feature_version"),
            "holdout_wape_mean": model.get("holdout_wape_mean"),
        },
        "n_zones": f.get("n_zones"),
        "rows_in_full": len(rows),
        "aggregate": {
            "sum_predicted_departures": round(sum(values), 2),
            "max_predicted_departures": round(max(values), 2) if values else None,
            "mean_predicted_departures": round(sum(values) / len(values), 3) if values else None,
        },
        "rows": [
            {"zone_id": r["zone_id"], "predicted_departures": r["predicted_departures"]}
            for r in kept
        ],
        "full_result_ref": _ref(raw, "get_model_forecast", {"top": len(rows)}),
    }


def check_model_forecast(raw: dict[str, Any], summary: dict[str, Any], zone_id: str) -> str:
    raw_val = next(
        r["predicted_departures"] for r in raw["forecast"]["forecasts"] if r["zone_id"] == zone_id
    )
    sum_val = next(r["predicted_departures"] for r in summary["rows"] if r["zone_id"] == zone_id)
    assert raw_val == sum_val, (raw_val, sum_val)
    assert summary["serving_hour"] == raw["forecast"]["serving_hour"]
    assert summary["model"]["algorithm"] == raw["forecast"]["model"]["algorithm"]
    assert summary["run_id"] == raw["run_id"] and summary["claim_status"] == raw["claim_status"]
    return (
        f"zone {zone_id} next-hour departures = {sum_val} in both; serving_hour, algorithm, "
        f"run_id and claim_status preserved"
    )


# --- scenario B: event evidence as-of cutoff --------------------------------------------------


def summarize_graph_context(raw: dict[str, Any], *, top_zones: int = 3) -> dict[str, Any]:
    """Every event keeps id/type/title/effect/severity and its full evidence sentence; the zone
    list is cut to the ``top_zones`` largest |forecast_delta| plus a count."""
    events = []
    for ev in raw.get("events", []):
        zones = sorted(ev.get("zones", []), key=lambda z: -abs(float(z["forecast_delta"])))
        events.append(
            {
                "event_id": ev["event_id"],
                "type": ev["type"],
                "title": ev["title"],
                "effect": ev["effect"],
                "severity": ev["severity"],
                "evidence": ev["evidence"],
                "zone_count": len(zones),
                "top_zones": [
                    {"zone_id": z["zone_id"], "forecast_delta": z["forecast_delta"]}
                    for z in zones[:top_zones]
                ],
            }
        )
    return {
        **_provenance(raw),
        "summary_of": "get_graph_context",
        "event_count": raw.get("event_count"),
        "events": events,
        "full_result_ref": _ref(
            raw, "get_graph_context", {"cutoff": raw.get("cutoff"), "max_events": 12}
        ),
    }


def check_graph_context(raw: dict[str, Any], summary: dict[str, Any]) -> str:
    raw_ids = [e["event_id"] for e in raw["events"]]
    sum_ids = [e["event_id"] for e in summary["events"]]
    assert raw_ids == sum_ids, (raw_ids, sum_ids)
    for r, s in zip(raw["events"], summary["events"], strict=True):
        assert r["evidence"] == s["evidence"] and r["type"] == s["type"]
        top_raw = max(r["zones"], key=lambda z: abs(float(z["forecast_delta"])))
        assert s["top_zones"][0]["zone_id"] == top_raw["zone_id"]
    assert summary["event_count"] == raw["event_count"] and summary["cutoff"] == raw["cutoff"]
    return (
        f"{len(sum_ids)} event ids, types, evidence sentences and the largest-delta zone per event "
        f"agree; cutoff preserved"
    )


# --- scenario C: operator state (shortage / surge, what rebalancing acts on) -------------------

_SCALAR_STAT_FIELDS = (
    "model_version",
    "feature_version",
    "note",
    "station_count",
    "total_bikes",
    "total_capacity",
    "total_docks_free",
    "system_utilization",
    "availability_counts",
    "stations_in_shortage",
    "total_shortage_units",
    "total_surplus_units",
    "available_event_count",
    "events_by_effect",
    "events_by_type",
    "affected_zone_count",
    "demand_delta_total",
    "demand_delta_max",
    "demand_delta_mean_affected",
)
_ZONE_FIELDS = ("zone_id", "en", "forecast_delta", "shortage", "worst_level", "utilization")


def summarize_operator_statistics(raw: dict[str, Any], *, top_n: int = 3) -> dict[str, Any]:
    """Keep every aggregate, the top-N surge zones and top-N shortage zones; drop the per-zone list."""
    s = raw["statistics"]
    zones = list(s.get("zones", []))
    surge = sorted(zones, key=lambda z: -float(z.get("forecast_delta", 0.0)))[:top_n]
    short = sorted(zones, key=lambda z: -float(z.get("shortage", 0)))[:top_n]
    return {
        **_provenance(raw),
        "summary_of": "get_operator_statistics",
        "aggregates": {k: s.get(k) for k in _SCALAR_STAT_FIELDS if k in s},
        "top_surge_zones": [{k: z.get(k) for k in _ZONE_FIELDS} for z in surge],
        "top_shortage_zones": [{k: z.get(k) for k in _ZONE_FIELDS} for z in short],
        "zones_in_full": len(zones),
        "full_result_ref": _ref(raw, "get_operator_statistics", {"cutoff": raw.get("cutoff")}),
    }


def check_operator_statistics(raw: dict[str, Any], summary: dict[str, Any]) -> str:
    s, a = raw["statistics"], summary["aggregates"]
    for k in (
        "stations_in_shortage",
        "total_shortage_units",
        "system_utilization",
        "station_count",
    ):
        assert a[k] == s[k], (k, a[k], s[k])
    raw_top = max(s["zones"], key=lambda z: float(z["forecast_delta"]))
    assert summary["top_surge_zones"][0]["zone_id"] == raw_top["zone_id"]
    assert summary["top_surge_zones"][0]["forecast_delta"] == raw_top["forecast_delta"]
    raw_short = max(s["zones"], key=lambda z: float(z["shortage"]))
    assert summary["top_shortage_zones"][0]["shortage"] == raw_short["shortage"]
    return (
        f"stations_in_shortage {a['stations_in_shortage']}, shortage units {a['total_shortage_units']}, "
        f"utilization {a['system_utilization']}, top surge zone {raw_top['zone_id']} "
        f"(delta {raw_top['forecast_delta']}) agree"
    )
