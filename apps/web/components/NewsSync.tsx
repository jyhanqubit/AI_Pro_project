"use client";

import { useState } from "react";
import { api, type NewsSyncResponse } from "@/lib/api";

// 실시간 뉴스 동기화: 버튼을 누르면 무료·키 불필요 GDELT DOC 2.0에서 최신 뉴스를 끌어와
// 벡터 스토어에 누적한다. 네트워크가 없으면 degraded 상태로 표시한다. compact 모드는 라이더용.
export function NewsSync({
  compact = false,
  onSynced,
}: {
  compact?: boolean;
  onSynced?: () => void;
}) {
  const [res, setRes] = useState<NewsSyncResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sync() {
    setLoading(true);
    try {
      const r = await api.newsSync();
      setRes(r);
      setError(null);
      if (r.status === "live" && r.added_to_index > 0) onSynced?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const button = (
    <button className="btn primary" onClick={sync} disabled={loading}>
      {loading ? "동기화 중…" : compact ? "🔄 최신 소식 동기화" : "🔄 뉴스 동기화"}
    </button>
  );

  const liveLine = res && res.status === "live" && (
    <div>
      <span className="badge live">
        <span className="dot" /> LIVE
      </span>{" "}
      <span className="muted small">
        {res.fetched}건 수집 · 인덱스 +{res.added_to_index} · 출처 {res.unique_sources}곳
      </span>
    </div>
  );

  const degradedLine = res && res.status === "degraded" && (
    <div className="notice" style={{ marginTop: compact ? 8 : 12 }}>
      지금은 실시간 뉴스를 불러올 수 없어요(네트워크 연결 없음). 잠시 후 다시 시도하거나, 네트워크가
      연결된 환경에서 이용해 주세요.
    </div>
  );

  // Compact (rider): a single button + a one-line status, no article list.
  if (compact) {
    return (
      <div className="card copilot">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div>
            <h2 style={{ fontSize: 15 }}>📰 최신 소식 받기</h2>
            <div className="sub">주변에 영향을 줄 만한 최신 뉴스를 지금 불러옵니다.</div>
          </div>
          {button}
        </div>
        {error && <div className="notice error" style={{ marginTop: 8 }}>{error}</div>}
        {res?.status === "live" && (
          <div style={{ marginTop: 8 }}>
            {liveLine}
            {res.articles.slice(0, 3).map((a) => (
              <div key={a.article_id} className="muted small" style={{ marginTop: 4 }}>
                • {a.title}
              </div>
            ))}
          </div>
        )}
        {degradedLine}
      </div>
    );
  }

  // Full (operator news screen): button + fetched article list.
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2>실시간 뉴스 동기화</h2>
          <div className="sub">무료·키 불필요 GDELT DOC 2.0에서 최신 모빌리티 뉴스를 지금 끌어옵니다.</div>
        </div>
        {button}
      </div>

      {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}

      {res?.status === "live" && (
        <div style={{ marginTop: 12 }}>
          {liveLine}
          <div className="grid" style={{ gap: 8, marginTop: 10 }}>
            {res.articles.slice(0, 8).map((a) => (
              <div key={a.article_id} className="event-line">
                <div>
                  <strong>{a.title}</strong>
                  <div className="muted small">
                    {a.source} · {a.published_at?.slice(0, 16).replace("T", " ")}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <p className="muted small" style={{ marginTop: 8 }}>{res.note}</p>
        </div>
      )}

      {degradedLine}
    </div>
  );
}
