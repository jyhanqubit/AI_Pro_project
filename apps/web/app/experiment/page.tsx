"use client";

import { useReplay } from "../providers";
import { useApi } from "@/lib/useApi";
import { api, type ExperimentOut, type ExperimentsResponse } from "@/lib/api";

// 실험 랩: 클러스터드 스위치백 실험으로 정책 효과를 "시뮬레이션"으로 비교하고,
// 어떤 값을 계산했는지 / 그 값이 무슨 뜻인지를 함께 설명한다. (실제 인과 lift 아님)

const LABEL: Record<string, string> = {
  AA: "A/A (동일 정책)",
  REC_ONLY: "추천만",
  STATIC_VS_DYNAMIC: "정적 vs 동적 크레딧",
  HYBRID: "하이브리드",
};

function pp(x: number): string {
  const v = (x * 100).toFixed(1);
  return `${x > 0 ? "+" : ""}${v}%p`;
}

function Verdict({ e }: { e: ExperimentOut }) {
  if (e.experiment_id === "AA") {
    return e.ci_excludes_zero ? (
      <span className="pill decrease">위양성 의심</span>
    ) : (
      <span className="pill increase">검증 통과 (효과 0)</span>
    );
  }
  return e.ci_excludes_zero ? (
    <span className="pill increase">효과 탐지</span>
  ) : (
    <span className="pill">불확실 (0 포함)</span>
  );
}

export default function ExperimentLab() {
  const { refreshKey } = useReplay();
  const ex = useApi<ExperimentsResponse>(() => api.experiments(), [refreshKey]);

  if (ex.error)
    return <div className="notice error">API에 연결할 수 없습니다 ({ex.error}).</div>;
  if (ex.loading || !ex.data) return <div className="notice">실험 결과를 불러오는 중…</div>;

  const d = ex.data;
  const aa = d.experiments.find((e) => e.experiment_id === "AA");
  const hybrid = d.experiments.find((e) => e.experiment_id === "HYBRID");

  return (
    <div className="grid" style={{ gap: 20 }}>
      <div className="hero">
        <h1>실험 랩 — 정책 효과 비교</h1>
        <p className="muted">
          공유 재고 간섭을 고려한 <strong>클러스터드 스위치백</strong> 설계(무작위화 단위 =
          존클러스터 × 시간블록)로 정책들을 비교합니다. 지표는 <strong>충족 수요율</strong>
          (자전거를 원할 때 실제로 빌린 비율)입니다.
        </p>
        <div className="notice warn" style={{ marginTop: 10 }}>
          ⚠ {d.disclaimer} — 아래 숫자는 <strong>선택 시뮬레이터</strong>가 만든 값이며 실제 사용자
          실험의 인과 효과가 아닙니다.
        </div>
      </div>

      {/* 1) 무엇을 얻었나 */}
      <div className="card">
        <h2>① 이 실험에서 무엇을 얻었나</h2>
        <div className="sub">
          A/A 검증이 통과(효과 ≈ 0)해야 나머지 결과를 신뢰할 수 있습니다 — 현재{" "}
          <strong>{d.aa_validation_passed ? "통과" : "실패"}</strong>.
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>실험</th>
                <th>ITT (평균 처리 효과)</th>
                <th>95% 신뢰구간</th>
                <th>CUPED 보정</th>
                <th>SRM</th>
                <th>판정</th>
              </tr>
            </thead>
            <tbody>
              {d.experiments.map((e) => (
                <tr key={e.experiment_id}>
                  <td>{LABEL[e.experiment_id] ?? e.experiment_id}</td>
                  <td className={`delta ${e.itt_effect > 0.0005 ? "up" : e.itt_effect < -0.0005 ? "down" : "flat"}`}>
                    {pp(e.itt_effect)}
                  </td>
                  <td className="mono" style={{ fontSize: 13 }}>
                    [{pp(e.itt_ci[0])}, {pp(e.itt_ci[1])}]
                  </td>
                  <td>{pp(e.cuped_itt_effect)}</td>
                  <td>{e.srm_ok ? "✓ 균형" : "✗ 불균형"}</td>
                  <td>
                    <Verdict e={e} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small" style={{ marginTop: 10 }}>
          단위 수 = 클러스터 × 시간블록. 각 실험은 대조군/처리군 각각 약 {aa ? aa.n_units / 2 : "—"}개
          단위를 관측합니다.
        </p>
      </div>

      {/* 1.5) 각 실험의 A/B 정의 */}
      <div className="card">
        <h2>각 실험의 A/B가 무엇인가</h2>
        <div className="sub">A = 대조군(control), B = 처리군(treatment). ITT는 B − A입니다.</div>
        <div className="grid" style={{ gap: 10 }}>
          {d.experiments.map((e) => (
            <div key={e.experiment_id} className="term">
              <div className="term-name">
                {LABEL[e.experiment_id] ?? e.experiment_id}{" "}
                <span className="muted small">— {e.hypothesis}</span>
              </div>
              <div className="ab-grid">
                <div className="ab-cell a">
                  <span className="ab-tag">A · 대조</span>
                  <strong>{e.arm_a.label}</strong>
                  <div className="muted small">{e.arm_a.description}</div>
                </div>
                <div className="ab-cell b">
                  <span className="ab-tag">B · 처리</span>
                  <strong>{e.arm_b.label}</strong>
                  <div className="muted small">{e.arm_b.description}</div>
                </div>
                <div className="ab-cell r">
                  <span className="ab-tag">결과 (B−A)</span>
                  <strong className={`delta ${e.itt_effect > 0.0005 ? "up" : e.itt_effect < -0.0005 ? "down" : "flat"}`}>
                    {pp(e.itt_effect)}
                  </strong>
                  <div className="muted small">
                    <Verdict e={e} />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 2) 어떤 값을 계산했고, 무슨 뜻인가 */}
      <div className="card">
        <h2>② 어떤 값을 계산했고, 무슨 뜻인가</h2>
        <div className="grid" style={{ gap: 10 }}>
          <Term
            term="ITT (평균 처리 효과)"
            what="처리군 평균 − 대조군 평균 (충족 수요율)."
            mean={`정책을 켰을 때 충족 수요율이 몇 %p 오르는지. 예: 하이브리드 ${
              hybrid ? pp(hybrid.itt_effect) : ""
            } = 약 ${hybrid ? (hybrid.itt_effect * 100).toFixed(0) : ""}%p 상승(시뮬레이션).`}
          />
          <Term
            term="95% 신뢰구간 (CI)"
            what="클러스터 블록-부트스트랩으로 추정한 효과의 불확실성 범위."
            mean="구간이 0을 포함하면 '효과가 있다고 말할 수 없음', 0을 벗어나면 '이 시뮬레이션에서 효과가 탐지됨'. 좁을수록 추정이 정밀."
          />
          <Term
            term="A/A 검증"
            what="같은 정책끼리(P0 vs P0) 비교한 대조 실험."
            mean={`효과가 0에 가깝고 CI가 0을 포함해야 정상. 이는 '실험 설계 자체가 가짜 효과를 만들지 않는다'는 증거. 현재 CI ${
              aa ? `[${pp(aa.itt_ci[0])}, ${pp(aa.itt_ci[1])}]` : ""
            } → ${d.aa_validation_passed ? "0 포함, 통과" : "0 미포함, 재점검 필요"}.`}
          />
          <Term
            term="CUPED 보정"
            what="사전기간(무행동) 성과를 공변량으로 써서 분산을 줄인 보정 추정치."
            mean="같은 효과라도 노이즈를 걷어내 더 안정적으로 추정. 원 ITT와 크게 다르면 사전 차이가 컸다는 뜻."
          />
          <Term
            term="SRM (표본 비율 불일치)"
            what="처리군/대조군 배정 비율이 설계값(50:50)에 맞는지 점검."
            mean="불균형(✗)이면 배정에 문제가 있어 결과를 신뢰할 수 없음. 여기선 스위치백 위상을 균형 배치해 propensity=0.5로 고정."
          />
          <Term
            term="스위치백 / 존클러스터×시간블록"
            what="무작위화 단위. 같은 지역군의 재고는 서로 영향을 주므로(간섭), 지역군을 시간블록마다 번갈아 처리."
            mean="개별 사용자 무작위화가 어려운 공유 재고 환경에서 시간에 걸쳐 처리를 교대해 편향을 줄이는 설계."
          />
        </div>
      </div>

      {/* 3) 결론 */}
      <div className="card">
        <h2>③ 결론 (시뮬레이션)</h2>
        <ul className="muted" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
          <li>
            <strong>A/A가 0을 포함해 통과</strong> → 아래 판독을 신뢰할 근거가 생깁니다.
          </li>
          <li>
            효과 크기: <strong>하이브리드 &gt; 동적 크레딧 &gt; 추천만</strong> 순으로 충족 수요율이
            올랐습니다(모두 CI가 0을 벗어나 탐지됨).
          </li>
          <li>
            <strong>동적 크레딧이 정적 크레딧보다 우수</strong> — 이벤트에 맞춰 크레딧을 조정한 효과.
          </li>
          <li>
            단, 이는 <strong>시뮬레이션 ITT</strong>이며 <strong>인과 lift가 아닙니다</strong>. 실제
            사용자 대상 무작위 실험이 생기기 전까지는 <span className="mono">simulated_experiment</span>
            로만 표기합니다.
          </li>
        </ul>
      </div>
    </div>
  );
}

function Term({ term, what, mean }: { term: string; what: string; mean: string }) {
  return (
    <div className="term">
      <div className="term-name">{term}</div>
      <div className="term-body">
        <div>
          <span className="term-k">계산</span> {what}
        </div>
        <div>
          <span className="term-k">의미</span> {mean}
        </div>
      </div>
    </div>
  );
}
