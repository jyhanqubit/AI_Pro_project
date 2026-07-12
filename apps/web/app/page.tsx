"use client";

import { useRouter } from "next/navigation";
import { useReplay } from "./providers";
import { useApi } from "@/lib/useApi";
import { api, type EventOut, type ForecastsResponse } from "@/lib/api";
import { deltaClass, signed, fmtTime } from "@/lib/format";

function shortZone(z: string): string {
  return `…${z.slice(-6)}`;
}

function EventAlert({ e }: { e: EventOut }) {
  return (
    <div className="card" style={{ padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <strong>{e.event_title}</strong>
        <span className={`pill ${e.demand_effect}`}>{e.demand_effect}</span>
      </div>
      <div className="sub" style={{ marginTop: 4 }}>
        {e.event_type} · severity {e.severity.toFixed(2)} · conf {e.confidence.toFixed(2)} · from{" "}
        {fmtTime(e.available_at)}
      </div>
      <div className="muted" style={{ fontSize: 13 }}>
        {e.evidence_spans.length} evidence span{e.evidence_spans.length === 1 ? "" : "s"} ·{" "}
        {e.locations.map((l) => l.name).join(", ")}
      </div>
    </div>
  );
}

export default function ControlTower() {
  const router = useRouter();
  const { refreshKey, setSelectedZone } = useReplay();
  const fc = useApi<ForecastsResponse>(() => api.forecasts(), [refreshKey]);
  const ev = useApi(() => api.events(), [refreshKey]);

  if (fc.error) {
    return (
      <div className="notice error">
        Cannot reach the API ({fc.error}). Run <span className="mono">make api</span> first.
      </div>
    );
  }
  if (fc.loading || !fc.data) return <div className="notice">Loading forecasts…</div>;

  const forecasts = fc.data.forecasts;
  const atRisk = forecasts.filter((f) => Math.abs(f.forecast_delta) > 0.001).length;
  const events = ev.data?.events ?? [];

  return (
    <div className="grid" style={{ gap: 20 }}>
      <div className="grid cols-3">
        <div className="card">
          <div className="sub">Events available</div>
          <div className="metric">{events.length}</div>
        </div>
        <div className="card">
          <div className="sub">Zones with event-driven shift</div>
          <div className="metric">{atRisk}</div>
        </div>
        <div className="card">
          <div className="sub">Forecast model</div>
          <div className="metric mono" style={{ fontSize: 16, marginTop: 8 }}>
            {fc.data.model_version}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            feature {fc.data.feature_version} · target {fc.data.target_name}
          </div>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Zone forecasts</h2>
          <div className="sub">
            Baseline vs event-aware ({fc.data.target_name}/hr). Click a zone to see why.
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Baseline</th>
                  <th>Event-aware</th>
                  <th>Δ</th>
                  <th>Exposure</th>
                </tr>
              </thead>
              <tbody>
                {forecasts.map((f) => (
                  <tr
                    key={f.zone_id}
                    className="zone-row"
                    onClick={() => {
                      setSelectedZone(f.zone_id);
                      router.push("/why");
                    }}
                  >
                    <td className="mono">{shortZone(f.zone_id)}</td>
                    <td>{f.baseline_forecast.toFixed(2)}</td>
                    <td>{f.event_aware_forecast.toFixed(2)}</td>
                    <td className={`delta ${deltaClass(f.forecast_delta)}`}>
                      {signed(f.forecast_delta)}
                    </td>
                    <td className="muted">{f.event_exposure.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h2>Event alerts</h2>
          <div className="sub">Available as-of the replay cutoff (availability rule).</div>
          {events.length === 0 ? (
            <div className="notice">No events available yet — advance the replay clock.</div>
          ) : (
            <div className="grid" style={{ gap: 10 }}>
              {events.map((e) => (
                <EventAlert key={e.event_id} e={e} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
