"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type ModelLiftResponse } from "@/lib/api";

// Model Lift Lab: 뉴스/이벤트/그래프 피처가 실제 예측 오차를 줄이는지(=이벤트 lift)를
// 측정된 Phase 06 B0~B4 ablation으로 보여준다. 측정값만, 조작 없음.

function Bar({ v, max }: { v: number; max: number }) {
  const pct = max > 0 ? Math.round((v / max) * 100) : 0;
  return (
    <div className="gauge" style={{ maxWidth: 160 }}>
      <div className="gauge-fill ok" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function ModelLiftLab() {
  const { refreshKey } = useReplay();
  const ml = useApi<ModelLiftResponse>(() => api.modelLift(), [refreshKey]);

  if (ml.error) return <div className="notice error">API에 연결할 수 없습니다 ({ml.error}).</div>;
  if (ml.loading || !ml.data) return <div className="notice">모델 lift 결과를 불러오는 중…</div>;

  const d = ml.data;
  const maxWape = Math.max(...d.ablation.map((a) => a.wape));
  const noLift = d.event_lift_verdict === "insufficient_event_overlap";
  const ev = d.event_verification as Record<string, string>;

  return (
    <div className="grid" style={{ gap: 20 }}>
      <div className="hero">
        <h1>Model Lift Lab — 뉴스/이벤트가 예측을 개선하나?</h1>
        <p className="muted">
          동일한 학습기·분할·타깃으로 <strong>B0 계절 naive → B1 과거+달력(M0) → B2 뉴스량 → B3
          이벤트 → B4 그래프(M1)</strong> 순서로 오차를 비교합니다. 측정된 Phase 06 홀드아웃 결과입니다
          (모델: <span className="mono">{d.model_version}</span>, 타깃: {d.target}).
        </p>
      </div>

      <div className="grid cols-3">
        <div className="card stat">
          <div className="sub">M0 기준 (B1) WAPE</div>
          <div className="metric">{d.m0_baseline.wape.toFixed(3)}</div>
          <div className="muted small">과거+달력. B0 대비 크게 개선</div>
        </div>
        <div className="card stat">
          <div className="sub">M1 이벤트반영 (B4) WAPE</div>
          <div className="metric">{d.m1_event_aware.wape.toFixed(3)}</div>
          <div className="muted small">M0 + 이벤트/그래프 피처</div>
        </div>
        <div className="card stat">
          <div className="sub">모델 기여 이벤트 lift</div>
          <div className={`metric ${noLift ? "" : "ok-text"}`}>
            {d.model_attributed_wape_lift.toFixed(3)}
          </div>
          <div className="muted small">M0 WAPE − M1 WAPE (양수면 개선)</div>
        </div>
      </div>

      {noLift && (
        <div className="notice warn">
          ⚠ 이벤트 lift = <strong>측정 불가 (insufficient_event_overlap)</strong>. 큐레이션된 이벤트가
          평가창 이후라 이벤트 피처가 전부 0 → B2~B4가 B1과 동일합니다. 숫자를 만들지 않고 정직하게
          표기합니다.
        </div>
      )}

      <div className="card">
        <h2>B0 → B4 오차 비교 (측정값)</h2>
        <div className="sub">WAPE·MAE·MASE 모두 낮을수록 좋음. 회색 막대는 WAPE 상대 크기.</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>단계</th>
                <th>WAPE</th>
                <th></th>
                <th>MAE</th>
                <th>MASE</th>
              </tr>
            </thead>
            <tbody>
              {d.ablation.map((a, i) => {
                const prev = i > 0 ? d.ablation[i - 1] : null;
                const improved = prev && a.wape < prev.wape - 1e-6;
                const same = prev && Math.abs(a.wape - prev.wape) <= 1e-6;
                return (
                  <tr key={a.arm}>
                    <td>
                      <strong>{a.arm}</strong> {a.label}
                      {improved && <span className="pill increase" style={{ marginLeft: 6 }}>개선</span>}
                      {same && <span className="pill" style={{ marginLeft: 6 }}>B1과 동일</span>}
                    </td>
                    <td className="mono">{a.wape.toFixed(3)}</td>
                    <td>
                      <Bar v={a.wape} max={maxWape} />
                    </td>
                    <td className="mono">{a.mae.toFixed(3)}</td>
                    <td className="mono">{a.mase.toFixed(3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>무슨 뜻인가</h2>
        <ul className="muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
          <li>
            <strong>과거+달력(M0)만으로도 계절 naive(B0)보다 크게 개선</strong> (WAPE{" "}
            {d.ablation[0]?.wape.toFixed(3)} → {d.m0_baseline.wape.toFixed(3)}). 시간/요일 패턴이
            수요의 큰 부분을 설명합니다.
          </li>
          <li>
            <strong>이벤트·그래프 피처(B2~B4)는 측정된 이득이 0</strong> — 평가창(6월 30일까지)과
            큐레이션 이벤트(7월 12일)가 겹치지 않아 피처가 전부 0이기 때문입니다
            (검증: <span className="mono">event_features_zero = {String(ev.event_features_zero)}</span>).
          </li>
          <li>
            즉 <strong>“이벤트가 예측을 개선한다”는 아직 주장할 수 없습니다.</strong> 숨기지 않고
            그대로 보고합니다.
          </li>
          <li>
            <strong>해결법</strong>: 평가창과 겹치는 6월 뉴스를 수집(<span className="mono">make
            v1-collect-news-live</span>)해 이벤트 피처가 0이 아니게 만든 뒤 재학습하면, 이 lift를 실제로
            측정할 수 있습니다(V1-04).
          </li>
        </ul>
        <p className="muted small" style={{ marginTop: 10 }}>{d.note}</p>
      </div>
    </div>
  );
}
