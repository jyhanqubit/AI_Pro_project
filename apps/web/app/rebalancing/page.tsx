"use client";

import { useEffect, useState } from "react";
import { useReplay } from "../providers";
import { api, type RebalancingResponse } from "@/lib/api";

// Phase 08: the Rebalancing Planner turns the event-aware forecast into a feasible relocation
// plan (the "Act" step). The plan comes from the classical solver over the curated station
// fixture; feasibility is checked before it is shown. Quantum Research Mode is never used here.
function shortZone(z: string): string {
  return z ? `…${z.slice(-6)}` : "—";
}

export default function RebalancingPlanner() {
  const { state, refreshKey } = useReplay();
  const [method, setMethod] = useState<"greedy" | "milp">("milp");
  const [result, setResult] = useState<RebalancingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cutoff = state?.cutoff ?? null;

  useEffect(() => {
    if (!cutoff) return;
    api
      .rebalancing(cutoff, method)
      .then((r) => {
        setResult(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [cutoff, method, refreshKey]);

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="card">
        <h2>Rebalancing Planner</h2>
        <div className="sub">Turn the forecast into a feasible relocation plan.</div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          {(["milp", "greedy"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMethod(m)}
              className={`pill ${method === m ? "active" : ""}`}
              style={{ cursor: "pointer", textTransform: "uppercase" }}
              aria-pressed={method === m}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="notice error">{error}</div>}

      {result && (
        <>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
              <div>
                <span className={`pill ${result.feasible ? "increase" : "decrease"}`}>
                  {result.feasible ? "feasible" : "INFEASIBLE"}
                </span>{" "}
                <span className="mono">{result.method}</span>
              </div>
              <div className="sub">
                vehicle capacity {result.vehicle_capacity} · moved {result.total_moved} bikes ·{" "}
                {result.total_distance_km.toFixed(2)} km
              </div>
            </div>
            {!result.feasible && result.infeasibility_reason && (
              <div className="notice error" style={{ marginTop: 8 }}>
                {result.infeasibility_reason}
              </div>
            )}
            <div className="grid" style={{ gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginTop: 12 }}>
              <div>
                <div className="sub">Shortage units</div>
                <strong>
                  {result.shortage_units_before} → {result.shortage_units_after}
                </strong>{" "}
                <span className="delta down">(−{result.shortage_reduction})</span>
              </div>
              <div>
                <div className="sub">Overflow units</div>
                <strong>
                  {result.overflow_units_before} → {result.overflow_units_after}
                </strong>
              </div>
              <div>
                <div className="sub">Operational cost</div>
                <strong>
                  {result.baseline_cost.toFixed(1)} → {result.total_cost.toFixed(1)}
                </strong>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>Moves</h2>
            {result.moves.length === 0 ? (
              <div className="notice">
                No relocation needed at this cutoff — inventory already meets targets.
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>From</th>
                      <th>To</th>
                      <th>Bikes</th>
                      <th>Distance (km)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.moves.map((m, i) => (
                      <tr key={i}>
                        <td className="mono">{m.origin_station_id}</td>
                        <td className="mono">{m.destination_station_id}</td>
                        <td>{m.quantity}</td>
                        <td>{m.distance_km.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card">
            <h2>Station inventory (before → after)</h2>
            <div className="sub">
              Targets are raised in event-exposed zones by the demo-heuristic forecast delta.
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Station</th>
                    <th>Zone</th>
                    <th>Bikes</th>
                    <th>Target</th>
                    <th>Shortage</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stations.map((s) => (
                    <tr key={s.station_id}>
                      <td>{s.name}</td>
                      <td className="mono">{shortZone(s.zone_id)}</td>
                      <td>
                        {s.bikes_before} → {s.bikes_after}
                      </td>
                      <td>
                        {s.target}
                        {s.target !== s.base_target && (
                          <span className="sub"> (base {s.base_target})</span>
                        )}
                      </td>
                      <td className={s.shortage_after < s.shortage_before ? "delta down" : ""}>
                        {s.shortage_before} → {s.shortage_after}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
              {result.note}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
