"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type AnomaliesResponse, type AnomalyAlertOut } from "@/lib/api";

// Anomaly Center: 4개 탐지기(데이터품질·재고·예측잔차·프록시수요) 결과 + 근본원인.
// 합성 결함은 명시 표기. 재고 급감은 이벤트로 근거 연결.

const TYPE_KO: Record<string, string> = {
  data_quality: "데이터 품질",
  inventory: "재고",
  forecast_residual: "예측 잔차",
  proxy_demand: "프록시 수요",
};
const ROOT_KO: Record<string, string> = {
  explained_by_event: "이벤트로 설명됨",
  partially_explained: "부분 설명",
  unexplained: "미설명",
  likely_data_quality: "데이터 품질 추정",
  inventory_dislocation: "재고 이탈",
};

function SevBadge({ s }: { s: number }) {
  const level = s >= 0.8 ? "low" : s >= 0.5 ? "tight" : "ok";
  return <span className={`status ${level}`}>{(s * 100).toFixed(0)}%</span>;
}

function RootPill({ status }: { status: string }) {
  const cls =
    status === "explained_by_event" ? "increase" : status === "unexplained" ? "decrease" : "";
  return <span className={`pill ${cls}`}>{ROOT_KO[status] ?? status}</span>;
}

export default function AnomalyCenter() {
  const { refreshKey } = useReplay();
  const an = useApi<AnomaliesResponse>(() => api.anomalies(), [refreshKey]);

  if (an.error) return <div className="notice error">API에 연결할 수 없습니다 ({an.error}).</div>;
  if (an.loading || !an.data) return <div className="notice">이상 탐지 결과를 불러오는 중…</div>;
  const d = an.data;

  return (
    <div className="grid" style={{ gap: 20 }}>
      <div className="hero">
        <h1>이상 탐지 센터 — Anomaly Center</h1>
        <p className="muted">
          4개 탐지기(<strong>데이터 품질 · 재고 · 예측 잔차 · 프록시 수요</strong>)가 스테이션 상태를
          감시하고, 이상을 <strong>근본 원인</strong>에 연결합니다. 운영 모드:{" "}
          <span className="mono">{d.mode}</span>.
        </p>
        <div className="notice warn" style={{ marginTop: 10 }}>
          ⚠ {d.note}
        </div>
      </div>

      <div className="grid cols-3">
        <div className="card stat">
          <div className="sub">탐지된 이상</div>
          <div className="metric">{d.n_alerts}건</div>
          <div className="muted small">합성 결함 {d.synthetic_fault_count}건 (실제 아님)</div>
        </div>
        <div className="card stat">
          <div className="sub">유형별</div>
          <div className="muted small" style={{ marginTop: 8, lineHeight: 1.9 }}>
            {Object.entries(d.by_type).map(([t, n]) => (
              <div key={t}>
                {TYPE_KO[t] ?? t}: <strong>{n}</strong>
              </div>
            ))}
          </div>
        </div>
        <div className="card stat">
          <div className="sub">근본 원인별</div>
          <div className="muted small" style={{ marginTop: 8, lineHeight: 1.9 }}>
            {Object.entries(d.by_root_cause).map(([r, n]) => (
              <div key={r}>
                {ROOT_KO[r] ?? r}: <strong>{n}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h2>이상 알림</h2>
        <div className="sub">심각도 높은 순. 재고/수요 이상은 이벤트 근거가 있으면 연결됩니다.</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>심각도</th>
                <th>유형 / 탐지기</th>
                <th>스테이션</th>
                <th>근본 원인</th>
                <th>근거</th>
                <th>합성?</th>
              </tr>
            </thead>
            <tbody>
              {d.alerts.map((a: AnomalyAlertOut) => (
                <tr key={a.anomaly_id}>
                  <td>
                    <SevBadge s={a.severity} />
                  </td>
                  <td>
                    <strong>{TYPE_KO[a.anomaly_type] ?? a.anomaly_type}</strong>
                    <div className="muted small mono">{a.detector}</div>
                  </td>
                  <td>{a.station_id}</td>
                  <td>
                    <RootPill status={a.root_cause_status} />
                  </td>
                  <td className="muted small">
                    {a.linked_event_ids.length > 0 ? (
                      <>
                        이벤트 {a.linked_event_ids.join(", ")}
                        {a.evidence_article_ids.length > 0 && (
                          <div className="mono">기사 {a.evidence_article_ids.join(", ")}</div>
                        )}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{a.is_synthetic_fault ? "예" : "아니오"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
