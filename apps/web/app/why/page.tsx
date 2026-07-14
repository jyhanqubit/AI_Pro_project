"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type ExplanationResponse, type ForecastsResponse, type TraceStep } from "@/lib/api";
import { deltaClass, signed } from "@/lib/format";
import { zoneLabel } from "@/lib/places";

const EFFECT_KO: Record<string, string> = {
  increase: "수요 증가",
  decrease: "수요 감소",
  unknown: "영향 불명",
};

function Driver({ d }: { d: TraceStep }) {
  return (
    <div className="card" style={{ padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <strong>{d.event_title}</strong>
        <span className={`pill ${d.demand_effect}`}>{EFFECT_KO[d.demand_effect] ?? d.demand_effect}</span>
      </div>
      <div className="sub">
        {d.event_type} · 심각도 {d.severity.toFixed(2)} · 신뢰도 {d.confidence.toFixed(2)}
      </div>

      <div className="trace">
        <span className="node">기사 {d.source_article_ids[0]}</span>
        <span className="arrow">→</span>
        <span className="node">이벤트</span>
        <span className="arrow">→</span>
        <span className="node">지역(H3)</span>
        <span className="arrow">→</span>
        <span className="node">지표</span>
      </div>

      <div className="muted" style={{ fontSize: 13, marginTop: 6 }}>
        근거 문장:
      </div>
      {d.evidence_spans.map((s, i) => (
        <div key={i} className="evidence">
          “{s.text}”
        </div>
      ))}

      <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
        기여한 그래프 지표:
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
    return <div className="notice error">API에 연결할 수 없습니다 ({fc.error}).</div>;
  if (!zone) return <div className="notice">아직 반영된 이벤트가 없어요 — 재생 시각을 앞으로 옮겨보세요.</div>;

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="card">
        <h2>이 지역은 왜 수요가 바뀌었나요?</h2>
        <div className="sub">기사 → 이벤트 → 지역(H3) → 지표 순서로, 근거 문장과 함께 추적합니다.</div>
        <label className="muted" style={{ fontSize: 13 }}>
          지역:{" "}
          <select
            value={zone}
            onChange={(e) => setSelectedZone(e.target.value)}
            style={{ marginLeft: 6 }}
          >
            {zones.map((z) => (
              <option key={z} value={z}>
                {zoneLabel(z)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {ex.loading || !ex.data ? (
        <div className="notice">설명을 불러오는 중…</div>
      ) : (
        <>
          <div className="grid cols-3">
            <div className="card">
              <div className="sub">평상시 예보</div>
              <div className="metric">{ex.data.baseline_forecast.toFixed(2)}</div>
            </div>
            <div className="card">
              <div className="sub">이벤트 반영 예보</div>
              <div className="metric">{ex.data.event_aware_forecast.toFixed(2)}</div>
            </div>
            <div className="card">
              <div className="sub">모델 기여 변화(Δ)</div>
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
