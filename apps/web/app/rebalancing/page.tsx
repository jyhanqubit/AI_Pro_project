"use client";

import { useEffect, useState } from "react";
import { useReplay } from "../providers";
import { api, type RebalancingResponse } from "@/lib/api";
import { stationPlace } from "@/lib/places";

// Phase 08: 재배치 계획(운영자용). 이벤트 반영 예보를 실제 이동 계획으로 바꾸는 "실행" 단계.
// 계획은 고전 solver가 큐레이션된 station fixture 위에서 만들며, 노출 전에 feasibility를 검증한다.
// Quantum Research Mode는 여기서 절대 쓰지 않는다.
const METHOD_KO: Record<string, string> = {
  milp: "MILP (정확 최적)",
  greedy: "Greedy (빠른 근사)",
};

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
        <h2>재배치 계획</h2>
        <div className="sub">예보를 실행 가능한(feasible) 자전거 이동 계획으로 바꿉니다.</div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          {(["milp", "greedy"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMethod(m)}
              className={`pill ${method === m ? "active" : ""}`}
              style={{ cursor: "pointer" }}
              aria-pressed={method === m}
            >
              {METHOD_KO[m]}
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
                  {result.feasible ? "실행 가능" : "실행 불가"}
                </span>{" "}
                <span className="mono">{result.method}</span>
              </div>
              <div className="sub">
                차량 적재량 {result.vehicle_capacity} · 이동 {result.total_moved}대 ·{" "}
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
                <div className="sub">부족량</div>
                <strong>
                  {result.shortage_units_before} → {result.shortage_units_after}
                </strong>{" "}
                <span className="delta down">(−{result.shortage_reduction})</span>
              </div>
              <div>
                <div className="sub">과잉량</div>
                <strong>
                  {result.overflow_units_before} → {result.overflow_units_after}
                </strong>
              </div>
              <div>
                <div className="sub">운영 비용</div>
                <strong>
                  {result.baseline_cost.toFixed(1)} → {result.total_cost.toFixed(1)}
                </strong>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>이동 계획</h2>
            {result.moves.length === 0 ? (
              <div className="notice">
                이 시각에는 이동이 필요 없어요 — 재고가 이미 목표를 충족합니다.
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>출발</th>
                      <th>도착</th>
                      <th>자전거</th>
                      <th>거리 (km)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.moves.map((m, i) => (
                      <tr key={i}>
                        <td>{stationPlace(m.origin_station_id).ko}</td>
                        <td>{stationPlace(m.destination_station_id).ko}</td>
                        <td>{m.quantity}대</td>
                        <td>{m.distance_km.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card">
            <h2>지역별 재고 (이동 전 → 후)</h2>
            <div className="sub">
              이벤트가 노출된 지역은 데모 heuristic 예보 델타만큼 목표 재고가 올라갑니다.
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>지역</th>
                    <th>자전거</th>
                    <th>목표</th>
                    <th>부족</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stations.map((s) => (
                    <tr key={s.station_id}>
                      <td>
                        {stationPlace(s.station_id).ko}
                        <div className="muted small">{stationPlace(s.station_id).en}</div>
                      </td>
                      <td>
                        {s.bikes_before} → {s.bikes_after}
                      </td>
                      <td>
                        {s.target}
                        {s.target !== s.base_target && (
                          <span className="sub"> (평상시 {s.base_target})</span>
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
