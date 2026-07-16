"use client";

import { useEffect, useState } from "react";
import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type EventOut, type RevenueResponse } from "@/lib/api";
import { deltaClass, signed } from "@/lib/format";
import { zoneLabel } from "@/lib/places";

const EFFECT_KO: Record<string, string> = {
  increase: "수요 증가",
  decrease: "수요 감소",
  unknown: "영향 불명",
};

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "up" | "down" | "flat";
}) {
  const color =
    tone === "up" ? "var(--good, #1b9c67)" : tone === "down" ? "var(--bad, #ce5a48)" : undefined;
  return (
    <div className="card" style={{ flex: 1, minWidth: 180 }}>
      <div className="sub" style={{ marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: "-0.02em", color }}>{value}</div>
      <div className="sub" style={{ marginTop: 4 }}>
        {sub}
      </div>
    </div>
  );
}

export default function ControlTower() {
  const { state, refreshKey } = useReplay();
  const ev = useApi<{ events: EventOut[] }>(() => api.events(), [refreshKey]);
  const [disabled, setDisabled] = useState<string[]>([]);
  const [result, setResult] = useState<RevenueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const cutoff = state?.cutoff ?? null;

  useEffect(() => {
    setDisabled([]);
  }, [refreshKey]);

  useEffect(() => {
    if (!cutoff) return;
    setLoading(true);
    api
      .revenue(cutoff, disabled)
      .then((r) => {
        setResult(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [cutoff, disabled]);

  const events = ev.data?.events ?? [];
  const d = result?.demand;
  const p = result?.pricing;
  const rev = result?.revenue;
  const nOn = events.length - disabled.length;

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="card">
        <h2>관제탑 — 이벤트 → 수요 → 가격 → 수익</h2>
        <div className="sub">
          뉴스·이벤트를 켜고 끄면, 그 이벤트를 반영한 수요예측이 다시 계산되고 → 동적요금(할증) →
          네트워크 수익까지 한 화면에서 함께 움직입니다. 모든 수치는{" "}
          <strong>SIMULATED SHADOW</strong>(데모 휴리스틱·정책 시뮬레이션)이며 실제 라이더에게
          부과되지 않습니다.
        </div>
      </div>

      <div className="card">
        <h2>이벤트 토글 {events.length > 0 && <span className="sub">({nOn}/{events.length} 켜짐)</span>}</h2>
        {events.length === 0 ? (
          <div className="notice">
            이 시각에는 반영할 이벤트가 없어요 — 상단 재생 시각을 이벤트 시점(예: 15:30 콘서트)으로
            옮겨보세요.
          </div>
        ) : (
          <div className="grid" style={{ gap: 8 }}>
            {events.map((e) => (
              <label key={e.event_id} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={!disabled.includes(e.event_id)}
                  onChange={(ev2) =>
                    setDisabled((prev) =>
                      ev2.target.checked
                        ? prev.filter((x) => x !== e.event_id)
                        : [...prev, e.event_id],
                    )
                  }
                />
                <span>
                  <strong>{e.event_title}</strong>{" "}
                  <span className={`pill ${e.demand_effect}`}>
                    {EFFECT_KO[e.demand_effect] ?? e.demand_effect}
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <div className="notice error">{error}</div>}

      {result && d && p && rev && (
        <>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <Stat
              label="① 수요 (이벤트 반영 vs 평상시)"
              value={`${signed(d.delta)} (${signed(d.delta_pct)}%)`}
              sub={`영향 지역 ${d.affected_zones}곳 · 평상시 ${d.baseline_total} → ${d.event_aware_total}`}
              tone={d.delta > 0 ? "up" : d.delta < 0 ? "down" : "flat"}
            />
            <Stat
              label="② 가격 (동적 할증)"
              value={`${p.surcharged_stations} 스테이션`}
              sub={`최고 ${p.max_multiplier.toFixed(2)}× 할증 (상한 ${p.cap.toFixed(2)}×, 기본요금 ${p.base_fare.toFixed(2)})`}
              tone={p.surcharged_stations > 0 ? "up" : "flat"}
            />
            <Stat
              label="③ 수익 (동적 vs 정액)"
              value={`${signed(rev.revenue_uplift)} (${signed(rev.revenue_uplift_pct)}%)`}
              sub={`정액 ${rev.flat_revenue.toFixed(1)} → 동적 ${rev.dynamic_revenue.toFixed(1)} · 대여 Δ ${signed(rev.fulfilled_delta)}`}
              tone={rev.revenue_uplift > 0 ? "up" : rev.revenue_uplift < 0 ? "down" : "flat"}
            />
          </div>

          <div className="card">
            <h2>할증이 걸린 스테이션</h2>
            <div className="sub">
              탄력성 {result.elasticity} 가정. 이벤트를 끄면 수요 급증이 사라져 할증·수익 상승분도 함께
              줄어듭니다{loading ? " (갱신 중…)" : ""}.
            </div>
            {result.stations.length === 0 ? (
              <div className="notice" style={{ marginTop: 8 }}>
                현재 토글 상태에서는 할증이 걸린 스테이션이 없습니다 (모두 기본요금).
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>지역</th>
                      <th>배수</th>
                      <th>요금</th>
                      <th>대여(가능/충족)</th>
                      <th>수익</th>
                      <th>사유</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.stations.map((s) => (
                      <tr key={s.station_id}>
                        <td>{zoneLabel(s.zone_id)}</td>
                        <td className={`delta ${deltaClass(s.multiplier - 1)}`}>
                          {s.multiplier.toFixed(2)}×
                        </td>
                        <td>{s.final_price.toFixed(2)}</td>
                        <td>
                          {s.available_bikes} / {s.fulfilled_rentals}
                        </td>
                        <td>{s.revenue.toFixed(1)}</td>
                        <td className="sub">{s.tier_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="notice">{result.note}</div>
        </>
      )}
    </div>
  );
}
