"use client";

import { useEffect, useState } from "react";
import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type EventOut, type ScenarioResponse } from "@/lib/api";
import { deltaClass, signed } from "@/lib/format";

function shortZone(z: string): string {
  return `…${z.slice(-6)}`;
}

export default function ScenarioLab() {
  const { state, refreshKey } = useReplay();
  const ev = useApi<{ events: EventOut[] }>(() => api.events(), [refreshKey]);
  const [disabled, setDisabled] = useState<string[]>([]);
  const [result, setResult] = useState<ScenarioResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cutoff = state?.cutoff ?? null;

  // Reset toggles when the replay clock moves.
  useEffect(() => {
    setDisabled([]);
  }, [refreshKey]);

  useEffect(() => {
    if (!cutoff) return;
    api
      .scenario(cutoff, disabled)
      .then((r) => {
        setResult(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [cutoff, disabled]);

  const events = ev.data?.events ?? [];

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="card">
        <h2>Scenario Lab</h2>
        <div className="sub">
          Toggle events off to compare the counterfactual forecast against the default.
        </div>
        {events.length === 0 ? (
          <div className="notice">No events at this cutoff — advance the replay clock.</div>
        ) : (
          <div className="grid" style={{ gap: 8 }}>
            {events.map((e) => (
              <label key={e.event_id} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={!disabled.includes(e.event_id)}
                  onChange={(ev2) =>
                    setDisabled((d) =>
                      ev2.target.checked
                        ? d.filter((x) => x !== e.event_id)
                        : [...d, e.event_id],
                    )
                  }
                />
                <span>
                  <strong>{e.event_title}</strong>{" "}
                  <span className={`pill ${e.demand_effect}`}>{e.demand_effect}</span>
                </span>
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <div className="notice error">{error}</div>}

      {result && (
        <div className="card">
          <h2>Baseline vs scenario</h2>
          <div className="sub">
            {disabled.length === 0
              ? "All events on (default)."
              : `${disabled.length} event(s) disabled.`}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Baseline</th>
                  <th>Default event-aware</th>
                  <th>Scenario</th>
                  <th>Δ vs default</th>
                </tr>
              </thead>
              <tbody>
                {result.zones.map((z) => (
                  <tr key={z.zone_id}>
                    <td className="mono">{shortZone(z.zone_id)}</td>
                    <td>{z.baseline_forecast.toFixed(2)}</td>
                    <td>{z.default_event_aware_forecast.toFixed(2)}</td>
                    <td>{z.scenario_forecast.toFixed(2)}</td>
                    <td className={`delta ${deltaClass(z.scenario_delta)}`}>
                      {signed(z.scenario_delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
