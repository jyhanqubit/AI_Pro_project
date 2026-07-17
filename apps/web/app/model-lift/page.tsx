"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type ModelLiftResponse, type PredictiveLiftResponse } from "@/lib/api";

// Model Lift Lab: 뉴스/이벤트/그래프 피처가 실제 예측 오차를 줄이는지(=이벤트 lift)를
// 측정된 Phase 06 B0~B4 ablation으로 보여준다. 측정된 값만 표시한다.

function Bar({ v, max }: { v: number; max: number }) {
  const pct = max > 0 ? Math.round((v / max) * 100) : 0;
  return (
    <div className="gauge" style={{ maxWidth: 160 }}>
      <div className="gauge-fill ok" style={{ width: `${pct}%` }} />
    </div>
  );
}

// Directional lift (방향별 리프트): measured June-holdout decomposition of *which direction* the event
// feature moved the forecast vs the demand+calendar baseline, and whether that direction reduced error.
// Static, self-contained visualization of real numbers from `python -m ml.forecasting.lift_direction`.
// The aggregate reconciles exactly with the headline (MAE 165.23 → 162.50, +2.73/row, n=3366).
type DirRow = {
  key: string;
  dir: string;
  tone: "increase" | "decrease" | "flat";
  rows: number;
  improvedPct: number;
  errReduction: number;
};

const DIR_ROWS: DirRow[] = [
  { key: "up", dir: "위로 밀어올림 (pred > 기준선)", tone: "increase", rows: 1394, improvedPct: 56.0, errReduction: 5.23 },
  { key: "down", dir: "아래로 끌어내림 (pred < 기준선)", tone: "decrease", rows: 1832, improvedPct: 62.0, errReduction: 1.03 },
  { key: "flat", dir: "거의 변화 없음", tone: "flat", rows: 140, improvedPct: 53.6, errReduction: 0.02 },
];

// Accuracy-improvement rate by direction — real numbers shown as text; bars are a visual aid only.
const IMPROVED_BARS: { label: string; pct: number; tone: "up" | "down" | "" }[] = [
  { label: "위로 밀어올림", pct: 56.0, tone: "up" },
  { label: "아래로 끌어내림", pct: 62.0, tone: "down" },
  { label: "수요 하락 + 아래로 보정", pct: 95.2, tone: "" },
];

function DirectionalLiftCard() {
  return (
    <div className="card">
      <h2>이벤트 피처는 수요를 낮추는 방향으로도 맞힌다 — 방향별 분석</h2>
      <div className="sub">
        동일한 6월 홀드아웃(테스트 3,366행)에서, 이벤트 피처가 예측을 기준선(수요+달력) 대비 어느
        방향으로 움직였는지, 그리고 그 방향이 실제 오차를 줄였는지를 측정했습니다.
      </div>
      <p className="muted" style={{ marginTop: 0, lineHeight: 1.9 }}>
        이벤트 피처는 <strong>양방향</strong>입니다 — 예측을 위로 올리기보다 아래로 끌어내리는 경우가 더
        많고(<span className="mono">1,832행</span> vs <span className="mono">1,394행</span>), 아래로
        내리는 보정이 더 자주 적중합니다(<strong>62% vs 56%</strong>). 가장 큰 이득은 예정된 폐쇄 등으로
        수요가 꺼지는 구간(dip)을 제대로 잡아낼 때 나옵니다. 이는 모델 기여(model-attributed)이며
        인과가 아니고, 자치구(borough) 단위는 H3 제품 그레인의 근사치입니다.
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>방향</th>
              <th>행 수</th>
              <th>정확도 개선(%)</th>
              <th>평균 오차 감소</th>
            </tr>
          </thead>
          <tbody>
            {DIR_ROWS.map((r) => (
              <tr key={r.key}>
                <td>
                  <span className={`pill ${r.tone === "flat" ? "" : r.tone}`}>{r.dir}</span>
                </td>
                <td className="mono">{r.rows.toLocaleString()}</td>
                <td className="mono">{r.improvedPct.toFixed(1)}%</td>
                <td className="mono">+{r.errReduction.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>
        정확도 개선(%) = 해당 방향에서 이벤트 반영 예측의 |오차|가 기준선보다 작아진 행의 비율. 평균 오차
        감소 단위는 라이드/구·시간.
      </p>

      <div style={{ marginTop: 14 }}>
        <div className="ts-title">방향별 정확도 개선율 비교</div>
        <div className="barlist" role="img" aria-label="방향별 정확도 개선율: 위로 밀어올림 56.0%, 아래로 끌어내림 62.0%, 수요 하락에 아래로 보정 95.2%">
          {IMPROVED_BARS.map((b) => (
            <div key={b.label} className="barlist-row">
              <div className="bl-label">{b.label}</div>
              <div className="bl-track">
                <div className={`bl-fill ${b.tone}`} style={{ width: `${b.pct}%` }} />
              </div>
              <div className="bl-value">{b.pct.toFixed(1)}%</div>
            </div>
          ))}
        </div>
      </div>

      <div className="notice warn" style={{ marginTop: 14 }}>
        <strong>가장 큰 단일 이득</strong>: 실제 수요가 기준선 예측보다 <strong>낮게</strong> 들어오고
        이벤트 피처가 예측을 아래로 끌어내린 <span className="mono">1,193행</span>에서{" "}
        <strong>95.2%</strong>가 정확도 개선, 평균 오차 감소 <strong>+17.4 라이드/구·시간</strong>. 즉
        예정된 폐쇄로 수요가 꺼지는 <strong>수요 하락(dip)</strong>을 잡아내는 것이 이벤트 피처의 핵심
        기여입니다.
      </div>

      <p className="muted small" style={{ marginTop: 10 }}>
        이 분해는 헤드라인과 정확히 일치합니다 (MAE 165.23 → 162.50, 행당 +2.73, n=3,366). 재현:{" "}
        <span className="mono">python -m ml.forecasting.lift_direction</span>
      </p>
    </div>
  );
}

// V2-02 predictive-lift protocol result (works offline; honestly blocked_data on the demo fixture).
function PredictiveLiftCard() {
  const { refreshKey } = useReplay();
  const pl = useApi<PredictiveLiftResponse>(() => api.predictiveLift(), [refreshKey]);
  if (pl.loading || !pl.data) return null;
  const d = pl.data;
  const gate = d.coverage_gate;
  const rows: { k: string; label: string; val: number; min: number; ok: boolean }[] = [
    { k: "unique_events", label: "고유 이벤트", val: d.coverage.unique_events, min: gate.min_unique_events, ok: d.coverage_conditions.unique_events },
    { k: "affected_zone_hours", label: "영향 zone-hour", val: d.coverage.affected_zone_hours, min: gate.min_affected_zone_hours, ok: d.coverage_conditions.affected_zone_hours },
    { k: "unique_sources", label: "고유 소스", val: d.coverage.unique_sources, min: gate.min_unique_sources, ok: d.coverage_conditions.unique_sources },
    { k: "event_types", label: "이벤트 타입", val: d.coverage.event_types, min: gate.min_event_types, ok: d.coverage_conditions.event_types },
  ];
  return (
    <div className="card">
      <h2>V2-02 Predictive Lift — 커버리지 게이트 & 판정</h2>
      <div className="sub">
        시계열 분할·purge/embargo·이벤트 블록 부트스트랩 CI·판정 규칙을 갖춘 프로토콜. 측정된 lift는
        커버리지 게이트 통과 <strong>그리고</strong> CI&gt;0 일 때만 주장합니다.
      </div>
      <div className="notice warn" style={{ marginTop: 8 }}>
        판정: <strong>{d.verdict}</strong> (claim_enabled={String(d.claim_enabled)}) — 데모 fixture는
        커버리지 게이트에 못 미쳐 <strong>blocked_data</strong>로 정직하게 비활성입니다.
      </div>
      <div className="table-wrap" style={{ marginTop: 8 }}>
        <table>
          <thead>
            <tr><th>커버리지 조건</th><th>측정값</th><th>게이트(≥)</th><th>통과</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.k}>
                <td>{r.label}</td>
                <td className="mono">{r.val}</td>
                <td className="mono">{r.min}</td>
                <td>
                  <span className={`pill ${r.ok ? "increase" : "decrease"}`}>{r.ok ? "통과" : "미달"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ marginTop: 10 }}>{d.note}</p>
    </div>
  );
}

export default function ModelLiftLab() {
  const { refreshKey } = useReplay();
  const ml = useApi<ModelLiftResponse>(() => api.modelLift(), [refreshKey]);

  if (ml.error) {
    // V1 measured ablation needs a training run (offline → unavailable). The V2 predictive-lift
    // protocol still renders honestly below.
    return (
      <div className="grid" style={{ gap: 20 }}>
        <PredictiveLiftCard />
        <DirectionalLiftCard />
        <div className="notice">
          V1 측정 ablation(B0–B4)은 학습 산출물이 있어야 표시됩니다 ({ml.error}). 위 V2-02
          predictive-lift 판정은 오프라인에서 동작합니다.
        </div>
      </div>
    );
  }
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

      <PredictiveLiftCard />

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
          평가창 이후라 이벤트 피처가 전부 0 → B2~B4가 B1과 동일합니다. 측정된 결과 그대로 표기합니다.
          (데모용 데이터입니다.)
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

      <DirectionalLiftCard />

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
