"use client";

import { useReplay } from "../providers";
import { OpsCopilot } from "@/components/OpsCopilot";
import { ModeBadge } from "@/components/ModeBadge";

// V2 operator Q&A tab: a first-class natural-language question interface for the operator. Answers
// are grounded in the same as-of artifacts the dashboards use (deterministic; GraphRAG/LLM when a key
// is present, rule-based otherwise). Numbers are never invented — they come from the tool results.

export default function AskPage() {
  const { state } = useReplay();
  const cutoff = state?.cutoff ?? null;

  return (
    <main>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>운영 도우미 — 질문하기</h1>
        {state && <ModeBadge mode={state.mode} />}
      </div>
      <p className="muted" style={{ marginTop: 0, lineHeight: 1.8 }}>
        자연어로 물어보면 <strong>대시보드와 동일한 as-of 데이터</strong>에 근거해 답합니다. 답변의
        모든 수치는 툴 결과에서 나오며 — 근거 없는 숫자는 만들지 않습니다. GPT/Claude 키가 있으면
        <span className="mono"> GraphRAG(LLM)</span>, 없으면 규칙 기반으로 동작하고 답변에
        <span className="mono"> answer_mode</span> 배지가 붙습니다.
      </p>
      <OpsCopilot cutoff={cutoff} />
    </main>
  );
}
