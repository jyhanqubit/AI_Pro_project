"use client";

import { useEffect, useState } from "react";
import { api, type NewsClustersResponse, type NewsSearchResponse } from "@/lib/api";

// 뉴스 벡터 검색 화면: FAISS 벡터 스토어에 누적된 뉴스에서 의미 기반 검색 +
// 같은 사건(same-event) 클러스터를 보여준다. 실시간 수집이 쌓일수록 커진다.

export default function NewsSearch() {
  const [query, setQuery] = useState("PATH suspended near Hoboken");
  const [res, setRes] = useState<NewsSearchResponse | null>(null);
  const [clusters, setClusters] = useState<NewsClustersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function runSearch(q: string) {
    setLoading(true);
    try {
      setRes(await api.newsSearch(q, 5));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void runSearch(query);
    api.newsClusters(0.3).then(setClusters).catch(() => setClusters(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="grid" style={{ gap: 20 }}>
      <div className="hero">
        <h1>뉴스 벡터 검색 — 누적 뉴스에서 찾기</h1>
        <p className="muted">
          FAISS 벡터 스토어에 <strong>실시간으로 쌓이는 뉴스</strong>를 의미 기반으로 검색하고, 같은
          사건을 다룬 기사들을 자동으로 묶습니다{" "}
          {res && (
            <span className="muted">
              (인덱스 {res.n_indexed}건 · 임베더 <span className="mono">{res.embedder}</span>)
            </span>
          )}
          .
        </p>
      </div>

      <div className="card">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch(query)}
            placeholder="예: PATH 지연 / Newport 콘서트 / Grove Street 폐쇄"
            aria-label="뉴스 검색어"
            style={{
              flex: 1,
              minWidth: 240,
              background: "var(--panel-2)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "8px 12px",
            }}
          />
          <button className="primary" onClick={() => runSearch(query)}>
            검색
          </button>
        </div>

        {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}

        {res && !error && (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>유사도</th>
                  <th>제목</th>
                  <th>출처</th>
                  <th>발행</th>
                </tr>
              </thead>
              <tbody>
                {res.results.map((r) => (
                  <tr key={r.article_id}>
                    <td className="mono">{r.score.toFixed(3)}</td>
                    <td>{r.title}</td>
                    <td className="muted">{r.source}</td>
                    <td className="muted small">{r.published_at.slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {loading && <div className="notice" style={{ marginTop: 10 }}>검색 중…</div>}
      </div>

      {clusters && (
        <div className="card">
          <h2>같은 사건 클러스터 ({clusters.n_clusters}개)</h2>
          <div className="sub">
            임베딩 유사도(cosine ≥ {clusters.threshold})로 연결 요소를 묶습니다. 한 클러스터 = 한
            사건 → 여러 언론사의 중복 기사를 한 이벤트로 처리합니다.
          </div>
          <div className="grid" style={{ gap: 10 }}>
            {clusters.clusters
              .filter((c) => c.size > 1)
              .map((c) => (
                <div key={c.cluster_id} className="term">
                  <div className="term-name">
                    #{c.cluster_id} · {c.size}건 묶음{" "}
                    <span className="pill increase" style={{ marginLeft: 6 }}>같은 사건</span>
                  </div>
                  <div className="muted">{c.representative_title}</div>
                  <div className="muted small mono" style={{ marginTop: 4 }}>
                    {c.article_ids.join(", ")}
                  </div>
                </div>
              ))}
            {clusters.clusters.filter((c) => c.size > 1).length === 0 && (
              <div className="notice">묶인 사건이 없습니다 (모두 단일 기사).</div>
            )}
          </div>
          <p className="muted small" style={{ marginTop: 10 }}>
            단일 기사 클러스터 {clusters.clusters.filter((c) => c.size === 1).length}개는 생략.
            오프라인 결정적 lexical 임베더 기준이며, 실서비스에서는 신경망 임베더로 교체 가능합니다.
          </p>
        </div>
      )}
    </div>
  );
}
