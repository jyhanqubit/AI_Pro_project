"use client";

import { useState } from "react";
import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type PriceQuote, type PricingResponse } from "@/lib/api";

// V2-05 dynamic fare simulator (operator). Every quote is a SIMULATED SHADOW quote — never applied
// to a rider. Surcharge is decided purely by station scarcity (no rider identity / protected
// attribute is ever an input); safety events and stale data fall back to the base fare. The demand
// delta driving the event component is the labelled demo-heuristic, not a measured model.

const REASON_KO: Record<string, string> = {
  scarcity: "부족(수요 압력)",
  base: "기본요금",
  stale: "stale 데이터 → 기본요금",
  safety_no_surcharge: "안전/긴급 이벤트 → 할증 금지",
};

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div className="pc-comp">
      <span className="pc-comp-k">{label}</span>
      <div className="pc-comp-track">
        <div className="pc-comp-fill" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="pc-comp-v">{value.toFixed(2)}</span>
    </div>
  );
}

function QuoteCard({ q }: { q: PriceQuote }) {
  const surcharged = q.scarcity_surcharge > 0.001;
  const credited = q.balancing_credit > 0.001;
  return (
    <div className={`card quote-card ${surcharged ? "surge" : credited ? "credit" : ""}`}>
      <div className="qc-head">
        <div>
          <div className="qc-name">{q.ko}</div>
          <div className="muted small">
            {q.en} · 자전거 {q.bikes} / 목표 {q.target}
          </div>
        </div>
        <div className="qc-price">
          <span className="qc-x">×{q.tier_multiplier.toFixed(2)}</span>
          <span className="qc-final">{q.final_price.toFixed(2)}</span>
        </div>
      </div>

      <div className="qc-line">
        <span className="muted">기본 {q.base_fare.toFixed(2)}</span>
        {surcharged && (
          <span className="delta up">+ 할증 {q.scarcity_surcharge.toFixed(2)}</span>
        )}
        {credited && (
          <span className="pc-credit">균형 크레딧 +{q.balancing_credit.toFixed(1)}</span>
        )}
        <span className="pc-reason">{REASON_KO[q.tier_reason] ?? q.tier_reason}</span>
      </div>

      <div className="pc-comps">
        <div className="muted small" style={{ marginBottom: 4 }}>
          부족 압력 점수 {q.scarcity_score.toFixed(2)} · 구성요소
        </div>
        <Bar label="부족 확률" value={q.components.shortage_probability} />
        <Bar label="정규화 격차" value={q.components.normalized_gap} />
        <Bar label="이벤트 영향" value={q.components.event_impact} />
        <Bar label="주변 여유(완화)" value={q.components.neighbor_buffer} />
      </div>

      <div className="qc-foot muted small">
        quote <span className="mono">{q.quote_id}</span>
        {q.guardrails.capped && <span className="pc-flag"> · 상한 도달(1.50)</span>}
      </div>
    </div>
  );
}

export default function PricingSimulator() {
  const { refreshKey } = useReplay();
  const [stale, setStale] = useState(false);
  const [safety, setSafety] = useState(false);
  const res = useApi<PricingResponse>(
    () => api.pricingQuote({ stale, safety }),
    [refreshKey, stale, safety],
  );

  if (res.error) {
    return (
      <div className="notice error">
        API에 연결할 수 없습니다 ({res.error}). <span className="mono">make api</span> 로 먼저 실행하세요.
      </div>
    );
  }

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="hero">
        <h1>동적 요금 시뮬레이터</h1>
        <p className="muted">
          부족(scarcity) 압력에 따라 상한이 있는 할증(최대 1.50배)과 잉여 스테이션 균형 크레딧을
          계산합니다. 라이더 신원·감면요금·보호속성은 입력에 쓰이지 않으며, 안전/긴급 이벤트나 stale
          데이터에는 할증하지 않습니다.
        </p>
      </div>

      <div className="notice warn">
        <strong>SIMULATED · SHADOW</strong> — 실제 라이더에게 적용되지 않는 시뮬레이션 견적입니다.
        탄력성/전환 추정치가 없어 결과는 simulated로만 제공됩니다.
      </div>

      {/* What-if scenario toggles */}
      <div className="card">
        <h2>시나리오 (what-if)</h2>
        <div className="sub">가드레일 동작을 확인하려면 시나리오를 켜보세요.</div>
        <div className="chips-row" style={{ marginTop: 8 }}>
          <button
            className={`chip ${!stale && !safety ? "active" : ""}`}
            onClick={() => {
              setStale(false);
              setSafety(false);
            }}
          >
            정상
          </button>
          <button className={`chip ${stale ? "active" : ""}`} onClick={() => setStale((v) => !v)}>
            stale 데이터
          </button>
          <button
            className={`chip low ${safety ? "active" : ""}`}
            onClick={() => setSafety((v) => !v)}
          >
            안전사고 이벤트
          </button>
        </div>
      </div>

      {res.loading || !res.data ? (
        <div className="notice">요금 견적을 계산하는 중…</div>
      ) : (
        <>
          <div className="muted small">
            설정 버전 <span className="mono">{res.data.pricing_config_version}</span> · 기본요금{" "}
            {res.data.base_fare.toFixed(2)} · 허용 tier {res.data.tiers.map((t) => `×${t.toFixed(2)}`).join(" / ")}
          </div>
          <div className="grid cols-2">
            {res.data.quotes.map((q) => (
              <QuoteCard key={q.station_id} q={q} />
            ))}
          </div>
          <p className="muted small">{res.data.note}</p>
        </>
      )}
    </div>
  );
}
