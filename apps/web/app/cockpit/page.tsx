"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type ClaimStatus, type CockpitMetric } from "@/lib/api";
import { ModeBadge } from "@/components/ModeBadge";

// V2-07 Cockpit: every headline metric is read live from a committed reports/v2/** artifact via
// GET /v2/cockpit/metrics and shown with its claim_status + artifact provenance. Nothing here is
// hard-coded — if the API cannot resolve a metric it renders as blocked, never a fabricated number.

const CLAIM_LABEL: Record<ClaimStatus, string> = {
  measured: "측정됨",
  offline_benchmark: "오프라인 벤치마크",
  simulated: "시뮬레이션",
  pending_live_label: "라벨 대기",
  assumption: "가정",
  blocked_data: "데이터 없음",
  blocked_external: "외부 차단",
  demo_fixture: "데모",
  research: "연구",
};

// measured / offline_benchmark can drive a decision (positive tone); simulated/assumption are
// comparison-only (neutral); blocked/pending are absence (muted-negative).
function claimTone(s: ClaimStatus): "increase" | "decrease" | "" {
  if (s === "measured" || s === "offline_benchmark") return "increase";
  if (s === "blocked_data" || s === "blocked_external" || s === "pending_live_label") return "decrease";
  return "";
}

function fmtValue(m: CockpitMetric): string {
  const v = m.envelope.value;
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    const u = (m.unit ?? "").toLowerCase();
    if (u.includes("usd")) return `${v < 0 ? "-" : ""}$${Math.abs(Math.round(v)).toLocaleString()}`;
    if (u === "wape") return v.toFixed(4);
    return Number.isInteger(v) ? String(v) : v.toFixed(2);
  }
  return String(v);
}

function MetricCard({ m }: { m: CockpitMetric }) {
  const e = m.envelope;
  const decision = e.claim_status === "measured" || e.claim_status === "offline_benchmark";
  const shown = fmtValue(m);
  // shrink long string values (e.g. model names) so they don't overflow the card
  const big = typeof e.value === "string" && shown.length > 10;
  return (
    <div className="card stat">
      <h2>{m.label}</h2>
      <div className="metric mono" style={big ? { fontSize: 18, wordBreak: "break-all", lineHeight: 1.3 } : undefined}>
        {shown}
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <span className={`pill ${claimTone(e.claim_status)}`} title="이 수치를 얼마나 신뢰할 수 있는가">
          {CLAIM_LABEL[e.claim_status]}
        </span>
        {!decision && e.claim_status === "simulated" && (
          <span className="muted" style={{ fontSize: 12 }}>가정 하 추정 · 제품 결정용 아님</span>
        )}
      </div>
      <div className="sub" style={{ marginBottom: 6 }}>{m.text}</div>
      {e.artifact_id ? (
        <div className="muted mono" style={{ fontSize: 11, wordBreak: "break-all" }}>
          출처: {e.artifact_id}
          <br />
          run: {e.run_id}
        </div>
      ) : (
        <div className="muted" style={{ fontSize: 12 }}>artifact 없음 — 수치를 지어내지 않음</div>
      )}
    </div>
  );
}

export default function CockpitPage() {
  const { refreshKey } = useReplay();
  const { data, error, loading } = useApi(() => api.cockpitMetrics("historical_replay"), [refreshKey]);

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>운영 콕핏 — 측정 지표</h1>
        {data && <ModeBadge mode={data.mode} />}
      </div>
      <p className="muted" style={{ marginTop: 0, lineHeight: 1.8 }}>
        모든 수치는 커밋된 <span className="mono">reports/v2/**</span> artifact에서 실시간으로 읽어오며,
        각 지표에는 <strong>신뢰도 라벨</strong>(측정됨 / 시뮬레이션 / …)과 <strong>출처 파일</strong>이
        함께 표시됩니다. 하드코딩된 숫자는 없습니다. <span className="mono">research</span> 결과는 운영
        화면에 노출되지 않습니다.
      </p>

      {loading && <p className="muted">불러오는 중…</p>}
      {error && <p className="pill decrease">API 오류: {error}</p>}
      {data && (
        <div className="grid cols-3">
          {data.metrics.map((m) => (
            <MetricCard key={m.key} m={m} />
          ))}
        </div>
      )}
    </main>
  );
}
