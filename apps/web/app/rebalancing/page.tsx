"use client";

import { useEffect, useState } from "react";
import { useReplay } from "../providers";
import { api, type AllocationResponse, type RebalancingResponse } from "@/lib/api";
import { stationPlace } from "@/lib/places";

// Phase 08: 재배치 계획(운영자용). 이벤트 반영 예보를 실제 이동 계획으로 바꾸는 "실행" 단계.
// 계획은 고전 solver가 큐레이션된 station fixture 위에서 만들며, 노출 전에 feasibility를 검증한다.
// Quantum Research Mode는 여기서 절대 쓰지 않는다.
const METHOD_KO: Record<string, string> = {
  milp: "MILP (정확 최적)",
  greedy: "Greedy (빠른 근사)",
};

// 추가 자전거 최적 분배: 운영자가 "지금 시스템에 n대가 있고, m대를 더 넣고 싶다"고 하면
// 그 m대를 부족한 대여소에 어떻게 나눠야 이익(부족 비용 감소)이 가장 큰지 계산한다.
// 목적이 분리·볼록이라 greedy 한계이익 배분이 전역 최적(백엔드에서 완전탐색과 일치 검증).
function AllocationPlanner({ cutoff, refreshKey }: { cutoff: string | null; refreshKey: number }) {
  const [extra, setExtra] = useState(6);
  const [res, setRes] = useState<AllocationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run(m: number) {
    if (!cutoff) return;
    setLoading(true);
    try {
      setRes(await api.allocateExtraBikes(m, cutoff));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  // Recompute when the replay cutoff changes (targets shift with events).
  useEffect(() => {
    void run(extra);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cutoff, refreshKey]);

  const totalBikes = res
    ? res.stations.reduce((a, s) => a + s.bikes_before, 0)
    : null;

  return (
    <div className="card">
      <h2>추가 자전거 최적 분배</h2>
      <div className="sub">
        지금 시스템의 자전거를 부족한 대여소에 더 넣을 때, 몇 대를 어디에 배치해야 이익이 가장 클지
        계산합니다. 넣을 자전거 수(m)를 입력하세요.
      </div>

      <div className="alloc-input">
        <label htmlFor="extra-bikes">추가할 자전거 (m)</label>
        <input
          id="extra-bikes"
          type="number"
          min={0}
          max={1000}
          value={extra}
          onChange={(e) => setExtra(Math.max(0, Math.min(1000, Number(e.target.value) || 0)))}
          onKeyDown={(e) => e.key === "Enter" && run(extra)}
        />
        <span className="unit">대</span>
        <button className="primary" onClick={() => run(extra)} disabled={loading || !cutoff}>
          {loading ? "계산 중…" : "최적 분배 계산"}
        </button>
      </div>

      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}

      {res && (
        <>
          <div className="alloc-kpis">
            <div className="alloc-kpi">
              <div className="k">현재 총 자전거</div>
              <div className="v">{totalBikes}대</div>
            </div>
            <div className="alloc-kpi">
              <div className="k">최적 배치</div>
              <div className="v ok-text">{res.placed}대</div>
              {res.leftover > 0 && <div className="sub">창고 보유 {res.leftover}대</div>}
            </div>
            <div className="alloc-kpi">
              <div className="k">부족 감소</div>
              <div className="v">
                {res.shortage_units_before} → {res.shortage_units_after}
                <span className="delta down"> (−{res.shortage_reduction})</span>
              </div>
            </div>
            <div className="alloc-kpi">
              <div className="k">운영 이익</div>
              <div className="v ok-text">+{res.benefit.toFixed(0)}</div>
              <div className="sub">비용 {res.cost_before.toFixed(0)} → {res.cost_after.toFixed(0)}</div>
            </div>
          </div>

          {res.leftover > 0 && (
            <div className="notice warn" style={{ marginTop: 12 }}>
              입력한 {res.extra_requested}대 중 <strong>{res.placed}대</strong>만 배치하면 이익이
              최대입니다. 나머지 {res.leftover}대는 목표를 이미 충족한 곳에 넣으면 과잉만 늘어나므로
              창고에 보유하는 것이 최적입니다.
            </div>
          )}

          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>지역</th>
                  <th>배치</th>
                  <th>재고 (전 → 후)</th>
                  <th>목표</th>
                  <th>부족 (전 → 후)</th>
                </tr>
              </thead>
              <tbody>
                {res.stations.map((s) => (
                  <tr key={s.station_id} className={s.added > 0 ? "alloc-hit" : ""}>
                    <td>
                      <strong>{s.ko}</strong>
                      <div className="muted small">{s.en}</div>
                    </td>
                    <td>
                      {s.added > 0 ? (
                        <span className="alloc-badge">+{s.added}대</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
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
          <p className="muted small" style={{ marginTop: 10 }}>
            {res.note}
          </p>
        </>
      )}
    </div>
  );
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
      <AllocationPlanner cutoff={cutoff} refreshKey={refreshKey} />

      <div className="card">
        <h2>대여소 간 재배치 (이동)</h2>
        <div className="sub">
          기존 자전거를 대여소 사이에서 옮겨 예보를 실행 가능한(feasible) 이동 계획으로 바꿉니다.
          (총 대수 보존)
        </div>
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
