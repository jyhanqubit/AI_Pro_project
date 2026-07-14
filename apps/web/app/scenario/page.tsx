"use client";

import { useEffect, useState } from "react";
import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type EventOut, type ScenarioResponse } from "@/lib/api";
import { deltaClass, signed } from "@/lib/format";
import { zoneLabel } from "@/lib/places";

const EFFECT_KO: Record<string, string> = {
  increase: "수요 증가",
  decrease: "수요 감소",
  unknown: "영향 불명",
};

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
        <h2>시나리오 비교</h2>
        <div className="sub">
          이벤트를 껐다 켜서, 그 이벤트가 없었다면 수요가 어땠을지(가정)를 기본값과 비교합니다.
        </div>
        {events.length === 0 ? (
          <div className="notice">이 시각에는 이벤트가 없어요 — 재생 시각을 앞으로 옮겨보세요.</div>
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
                  <span className={`pill ${e.demand_effect}`}>{EFFECT_KO[e.demand_effect] ?? e.demand_effect}</span>
                </span>
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <div className="notice error">{error}</div>}

      {result && (
        <div className="card">
          <h2>기본값 vs 시나리오</h2>
          <div className="sub">
            {disabled.length === 0
              ? "모든 이벤트 켜짐 (기본값)."
              : `이벤트 ${disabled.length}건 꺼짐.`}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>지역</th>
                  <th>평상시</th>
                  <th>기본(이벤트 반영)</th>
                  <th>시나리오</th>
                  <th>기본 대비 Δ</th>
                </tr>
              </thead>
              <tbody>
                {result.zones.map((z) => (
                  <tr key={z.zone_id}>
                    <td>{zoneLabel(z.zone_id)}</td>
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
