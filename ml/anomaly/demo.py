"""Anomaly detection demo (offline): python -m ml.anomaly.demo."""

from __future__ import annotations

from ml.anomaly import attribute_root_cause, detect_all
from ml.anomaly.scenario import build_demo_scenario


def main() -> None:
    obs, events = build_demo_scenario()
    alerts = attribute_root_cause(detect_all(obs), events)
    clean = [o for o in obs if not o.is_synthetic_fault]

    print(f"{len(alerts)} alert(s); false alerts on clean baseline: {len(detect_all(clean))}")
    for a in alerts:
        links = f" <- {a.linked_event_ids}" if a.linked_event_ids else ""
        print(f"  [{a.severity:.2f}] {a.anomaly_type.value:16s} {a.station_id:12s} "
              f"{a.detector:15s} {a.root_cause_status.value}{links}  synth={a.is_synthetic_fault}")


if __name__ == "__main__":
    main()
