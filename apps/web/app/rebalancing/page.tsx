"use client";

import { useEffect, useState } from "react";
import { useReplay } from "../providers";
import {
  api,
  type RebalancingResponse,
  type SupplyAllocationResponse,
} from "@/lib/api";
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

  // 신규 자전거 투입 배분: 운영자가 추가 대수(m)를 입력하면 이익이 가장 큰 배분을 계산한다.
  const [extraBikes, setExtraBikes] = useState<string>("10");
  const [placeSurplus, setPlaceSurplus] = useState<boolean>(false);
  const [alloc, setAlloc] = useState<SupplyAllocationResponse | null>(null);
  const [allocError, setAllocError] = useState<string | null>(null);

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

  const m = Number.parseInt(extraBikes, 10);
  const mValid = Number.isFinite(m) && m >= 0;

  useEffect(() => {
    if (!cutoff || !mValid) return;
    api
      .allocate(cutoff, m, placeSurplus)
      .then((r) => {
        setAlloc(r);
        setAllocError(null);
      })
      .catch((e) => setAllocError(e instanceof Error ? e.message : String(e)));
  }, [cutoff, m, mValid, placeSurplus, refreshKey]);

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

      <div className="card">
        <h2>신규 자전거 투입 배분</h2>
        <div className="sub">
          지금 배치된 자전거는 그대로 두고, 추가로 넣을 대수(m)를 입력하면 이익(운영 비용 절감)이
          가장 큰 배분을 계산합니다. 부족한 지역부터 채우고, 남는 자전거는 예비로 보류합니다.
        </div>
        <div style={{ display: "flex", gap: 12, marginTop: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="sub">추가 투입 대수 (m)</span>
            <input
              type="number"
              min={0}
              step={1}
              value={extraBikes}
              onChange={(e) => setExtraBikes(e.target.value)}
              aria-label="추가로 투입할 자전거 대수"
              style={{
                width: 140,
                padding: "8px 10px",
                borderRadius: 8,
                border: "1px solid var(--border, #ccc)",
                background: "transparent",
                color: "inherit",
                fontSize: 16,
              }}
            />
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "center", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={placeSurplus}
              onChange={(e) => setPlaceSurplus(e.target.checked)}
            />
            <span className="sub">남는 자전거도 전량 배치 (잉여는 순이익 감소)</span>
          </label>
        </div>
        {!mValid && (
          <div className="notice error" style={{ marginTop: 8 }}>
            0 이상의 정수를 입력하세요.
          </div>
        )}
        {allocError && (
          <div className="notice error" style={{ marginTop: 8 }}>
            {allocError}
          </div>
        )}
      </div>

      {alloc && mValid && (
        <>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
              <div>
                현재 배치 <strong>{alloc.current_total_bikes}</strong>대 + 신규{" "}
                <strong>{alloc.extra_bikes}</strong>대
              </div>
              <div className="sub mono">{alloc.solver}</div>
            </div>
            <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 12 }}>
              <div>
                <div className="sub">부족 해소 투입</div>
                <strong>{alloc.to_deficit}대</strong>
              </div>
              <div>
                <div className="sub">잉여 배치</div>
                <strong>{alloc.surplus_placed}대</strong>
              </div>
              <div>
                <div className="sub">예비 보류</div>
                <strong>{alloc.held}대</strong>
              </div>
              <div>
                <div className="sub">순이익 (비용 절감)</div>
                <strong className={alloc.benefit > 0 ? "delta down" : alloc.benefit < 0 ? "decrease" : ""}>
                  {alloc.benefit > 0 ? "+" : ""}
                  {alloc.benefit.toFixed(1)}
                </strong>
              </div>
            </div>
            <div style={{ marginTop: 12 }}>
              <div className="sub">부족량</div>
              <strong>
                {alloc.shortage_units_before} → {alloc.shortage_units_after}
              </strong>{" "}
              {alloc.shortage_reduction > 0 && (
                <span className="delta down">(−{alloc.shortage_reduction})</span>
              )}
            </div>
            {alloc.held > 0 && (
              <div className="notice" style={{ marginTop: 12 }}>
                {alloc.shortage_units_after === 0
                  ? `부족을 모두 해소하는 데 ${alloc.to_deficit}대면 충분합니다. 나머지 ${alloc.held}대는 예비로 보류하는 것이 순이익이 가장 큽니다.`
                  : `${alloc.held}대는 남는 독(dock)이 없어 배치할 수 없습니다.`}
              </div>
            )}
          </div>

          <div className="card">
            <h2>지역별 투입 배분 (투입 전 → 후)</h2>
            <div className="sub">
              이벤트가 노출된 지역은 데모 heuristic 예보 델타만큼 목표 재고가 올라갑니다.
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>지역</th>
                    <th>투입</th>
                    <th>자전거</th>
                    <th>목표</th>
                    <th>부족</th>
                  </tr>
                </thead>
                <tbody>
                  {alloc.allocations.map((s) => (
                    <tr key={s.station_id}>
                      <td>
                        {stationPlace(s.station_id).ko}
                        <div className="muted small">{stationPlace(s.station_id).en}</div>
                      </td>
                      <td className={s.added > 0 ? "delta up" : ""}>
                        {s.added > 0 ? `+${s.added}대` : "—"}
                      </td>
                      <td>
                        {s.bikes_before} → {s.bikes_after}
                        <span className="sub"> / {s.capacity}</span>
                      </td>
                      <td>
                        {s.target}
                        {s.target !== s.base_target && (
                          <span className="sub"> (평상시 {s.base_target})</span>
                        )}
                      </td>
                      <td className={s.deficit_after < s.deficit_before ? "delta down" : ""}>
                        {s.deficit_before} → {s.deficit_after}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
              {alloc.note}
            </p>
          </div>
        </>
      )}

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
