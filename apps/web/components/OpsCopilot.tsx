"use client";

import { useState } from "react";
import Link from "next/link";
import { api, type OpsAskResponse } from "@/lib/api";

// Operator copilot: ask in natural language. Every fact comes from the same artifacts the dashboards
// render (/v2/operator/ask, deterministic + grounded); answers can deep-link to a screen. GraphRAG
// (LLM) when a key is configured, else rule-based — the response carries answer_mode + citations.
const OPS_CHIPS = ["지금 현황", "부족 대여소", "수요 급증", "요금 상태"];

export function OpsCopilot({ cutoff }: { cutoff: string | null }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<OpsAskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(query: string) {
    const text = query.trim();
    if (!text || !cutoff) return;
    setLoading(true);
    try {
      setRes(await api.opsAsk(text, cutoff));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card copilot">
      <h2>🛠 운영 도우미에게 물어보세요</h2>
      <div className="sub">
        as-of 이벤트 그래프에 근거해 답합니다. GPT/Claude 키를 설정하면 GraphRAG(LLM)로,
        없으면 규칙 기반으로 자동 동작합니다 (오프라인 · 임의 SQL 없음 · 숫자는 대시보드와 동일 출처).
      </div>
      <div className="searchbar" style={{ marginTop: 10 }}>
        <span className="search-icon" aria-hidden="true">💬</span>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(q)}
          placeholder="예: 지금 시스템 현황 어때? · 부족한 곳 어디야 · 요금 화면 열어"
          aria-label="운영 도우미 질문"
        />
        <button className="btn primary" onClick={() => ask(q)} disabled={loading || !cutoff}>
          {loading ? "…" : "물어보기"}
        </button>
      </div>
      <div className="copilot-chips">
        {OPS_CHIPS.map((c) => (
          <button
            key={c}
            className="chip"
            onClick={() => {
              setQ(c);
              void ask(c);
            }}
          >
            {c}
          </button>
        ))}
      </div>
      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
      {res && (
        <div className={`copilot-answer ${res.supported ? "" : "unsupported"}`}>
          <div className="copilot-badge-row">
            {res.answer_mode === "graphrag_llm" ? (
              <span className="pill increase" title="LLM이 as-of 이벤트 그래프에 근거해 생성한 답변">
                ⚡ GraphRAG · {(res.llm_provider ?? "llm").toUpperCase()}
              </span>
            ) : (
              <span className="pill" title="규칙 기반(비-LLM) · 대시보드와 동일한 데이터">
                📐 규칙 기반
              </span>
            )}
            {typeof res.grounded_event_count === "number" && (
              <span className="muted small">근거 이벤트 {res.grounded_event_count}건</span>
            )}
          </div>
          <p className="answer-text">{res.answer}</p>
          {res.citations && res.citations.length > 0 && (
            <div className="copilot-citations">
              <span className="muted small">인용된 이벤트(그래프에서 검증됨):</span>
              <ul>
                {res.citations.map((c) => (
                  <li key={c.event_id}>
                    <code>{c.event_id}</code> — {c.title}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {res.link && (
            <Link href={res.link.href} className="btn primary ops-link">
              {res.link.label} →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
