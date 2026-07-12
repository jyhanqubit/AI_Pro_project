"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type ExplanationResponse, type ForecastsResponse, type TraceStep } from "@/lib/api";
import { deltaClass, signed } from "@/lib/format";

function Driver({ d }: { d: TraceStep }) {
  return (
    <div className="card" style={{ padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <strong>{d.event_title}</strong>
        <span className={`pill ${d.demand_effect}`}>{d.demand_effect}</span>
      </div>
      <div className="sub">
        {d.event_type} · severity {d.severity.toFixed(2)} · confidence {d.confidence.toFixed(2)}
      </div>

      <div className="trace">
        <span className="node">Article {d.source_article_ids[0]}</span>
        <span className="arrow">→</span>
        <span className="node">Event</span>
        <span className="arrow">→</span>
        <span className="node">H3 Zone</span>
        <span className="arrow">→</span>
        <span className="node">Feature</span>
      </div>

      <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>
        Grounded evidence:
      </div>
      {d.evidence_spans.map((s, i) => (
        <div key={i} className="evidence">
          “{s.text}”
        </div>
      ))}

      <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
        Contributed graph features:
      </div>
      <div className="table-wrap">
        <table>
          <tbody>
            {Object.entries(d.contributed_features).map(([k, v]) => (
              <tr key={k}>
                <td className="mono">{k}</td>
                <td>{v.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function WhyChanged() {
  const { refreshKey, selectedZone, setSelectedZone } = useReplay();
  const fc = useApi<ForecastsResponse>(() => api.forecasts(), [refreshKey]);

  const zones = fc.data?.forecasts.map((f) => f.zone_id) ?? [];
  const zone = selectedZone && zones.includes(selectedZone) ? selectedZone : zones[0] ?? null;

  const ex = useApi<ExplanationResponse | null>(
    () => (zone ? api.explanation(zone) : Promise.resolve(null)),
    [refreshKey, zone],
  );

  if (fc.error)
    return <div className="notice error">Cannot reach the API ({fc.error}).</div>;
  if (!zone) return <div className="notice">No zones yet — advance the replay clock.</div>;

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="card">
        <h2>Why did this zone change?</h2>
        <div className="sub">Article → Event → H3 Zone → Feature, with grounded evidence.</div>
        <label className="muted" style={{ fontSize: 13 }}>
          Zone:{" "}
          <select
            value={zone}
            onChange={(e) => setSelectedZone(e.target.value)}
            style={{ marginLeft: 6 }}
          >
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </label>
      </div>

      {ex.loading || !ex.data ? (
        <div className="notice">Loading explanation…</div>
      ) : (
        <>
          <div className="grid cols-3">
            <div className="card">
              <div className="sub">Baseline</div>
              <div className="metric">{ex.data.baseline_forecast.toFixed(2)}</div>
            </div>
            <div className="card">
              <div className="sub">Event-aware</div>
              <div className="metric">{ex.data.event_aware_forecast.toFixed(2)}</div>
            </div>
            <div className="card">
              <div className="sub">Model-attributed Δ</div>
              <div className={`metric delta ${deltaClass(ex.data.forecast_delta)}`}>
                {signed(ex.data.forecast_delta)}
              </div>
            </div>
          </div>

          {ex.data.drivers.length === 0 ? (
            <div className="notice">{ex.data.note}</div>
          ) : (
            <>
              <div className="notice warn">{ex.data.note}</div>
              <div className="grid" style={{ gap: 12 }}>
                {ex.data.drivers.map((d) => (
                  <Driver key={d.event_id} d={d} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
