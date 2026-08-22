"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useReplay } from "./providers";
import { useApi } from "@/lib/useApi";
import {
  api,
  type AvailabilityLevel,
  type EventOut,
  type RiderAskResponse,
  type TripPlan,
  type StationHit,
  type StationSearchResponse,
} from "@/lib/api";
import { signed } from "@/lib/format";
import { StationMap } from "@/components/StationMap";
import { NewsSync } from "@/components/NewsSync";

// Rider home, redesigned V2 (usability update).
// Inspired by consumer bike-share apps (따릉이 / Citi Bike): a prominent search bar,
// an at-a-glance availability summary, quick filter chips, a clean station list, and a
// tap-to-open station detail sheet. Data comes from the offline V2 search endpoint
// (/v2/rider/stations/search), which hydrates each station with as-of inventory + the
// event-aware demand delta. Search filtering is instant/client-side over that list.

const ADVICE: Record<AvailabilityLevel, string> = {
  plenty: "자전거가 넉넉해요 — 지금 빌리기 좋아요.",
  ok: "빌릴 수 있어요.",
  tight: "재고가 빠듯해요 — 서두르는 게 좋아요.",
  low: "수요가 몰려요 — 서두르거나 여유 지역을 이용하세요.",
};

type FilterKey = "all" | "good" | "low";

function LevelPill({ level, label }: { level: AvailabilityLevel; label: string }) {
  return <span className={`status ${level}`}>{label}</span>;
}

function Gauge({ bikes, capacity, level }: { bikes: number; capacity: number; level: string }) {
  const pct = capacity > 0 ? Math.min(100, Math.round((bikes / capacity) * 100)) : 0;
  return (
    <div className="gauge" aria-hidden="true">
      <div className={`gauge-fill ${level}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function StationRow({ s, onOpen }: { s: StationHit; onOpen: () => void }) {
  const surge = s.demand_delta > 0.001;
  return (
    <button className={`station-row ${s.level}`} onClick={onOpen}>
      <div className="sr-bar" aria-hidden="true" />
      <div className="sr-main">
        <div className="sr-title">
          <span className="sr-name">{s.ko}</span>
          {surge && <span className="sr-surge" title="이벤트로 수요 증가">🔥 수요↑</span>}
        </div>
        <div className="sr-sub">
          {s.en} · {s.area}
        </div>
        <Gauge bikes={s.bikes} capacity={s.capacity} level={s.level} />
      </div>
      <div className="sr-right">
        <div className="sr-count">
          <span className="n">{s.bikes}</span>
          <span className="u">대</span>
        </div>
        <LevelPill level={s.level} label={s.level_label} />
        <div className="sr-docks">반납 {s.docks_free}칸</div>
      </div>
    </button>
  );
}

function StationSheet({
  s,
  onClose,
  onWhy,
}: {
  s: StationHit;
  onClose: () => void;
  onWhy: () => void;
}) {
  const surge = s.demand_delta > 0.001;
  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`${s.ko} 상세`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-grip" aria-hidden="true" />
        <div className="sheet-head">
          <div>
            <div className="sheet-name">{s.ko}</div>
            <div className="rider-sub">
              {s.en} · {s.area}
            </div>
          </div>
          <LevelPill level={s.level} label={s.level_label} />
        </div>

        <div className="sheet-stats">
          <div className="ss-cell">
            <div className="ss-k">빌릴 수 있는 자전거</div>
            <div className={`ss-v ${s.level}`}>
              {s.bikes}
              <span className="unit">대</span>
            </div>
          </div>
          <div className="ss-cell">
            <div className="ss-k">반납 여유</div>
            <div className="ss-v">
              {s.docks_free}
              <span className="unit">칸</span>
            </div>
          </div>
          <div className="ss-cell">
            <div className="ss-k">정원</div>
            <div className="ss-v">
              {s.capacity}
              <span className="unit">대</span>
            </div>
          </div>
        </div>

        <Gauge bikes={s.bikes} capacity={s.capacity} level={s.level} />
        <p className="sheet-advice">{ADVICE[s.level]}</p>

        {surge ? (
          <div className="sheet-surge">
            <div className="sheet-surge-head">이벤트로 수요가 늘고 있어요</div>
            <div className="sheet-surge-body">
              이 지역 예상 수요 {s.baseline_forecast.toFixed(1)} →{" "}
              <strong>{s.event_aware_forecast.toFixed(1)}</strong> /시간{" "}
              <span className="delta up">{signed(s.demand_delta, 1)}</span>
            </div>
            <button className="btn primary" onClick={onWhy}>
              이 지역이 붐비는 이유 보기 →
            </button>
          </div>
        ) : (
          <div className="sheet-normal muted small">
            현재 이 지역 수요는 평상시 수준이에요. 공개된 이벤트 영향이 없습니다.
          </div>
        )}

        <button className="btn sheet-close" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}

// Rider copilot: ask in natural language. The answer + every number come from the deterministic,
// tool-grounded backend (/v2/rider/ask) — no LLM key; numbers are copied straight from live state.
const COPILOT_CHIPS = [
  "빌리기 좋은 곳",
  "곧 부족한 곳",
  "반납 여유",
  "지금 무슨 일 있어?",
];

function RiderCopilot({
  cutoff,
  onOpen,
}: {
  cutoff: string | null;
  onOpen: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<RiderAskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(query: string) {
    const text = query.trim();
    if (!text || !cutoff) return;
    setLoading(true);
    try {
      setRes(await api.riderAsk(text, cutoff));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card copilot">
      <h2>🚲 자전거 도우미에게 물어보세요</h2>
      <div className="sub">
        자연어로 물어보면 지금 재고를 바탕으로 답해드려요 (규칙 기반 · 오프라인).
      </div>

      <div className="searchbar" style={{ marginTop: 10 }}>
        <span className="search-icon" aria-hidden="true">💬</span>
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(q)}
          placeholder="예: 시청 근처 자전거 있어? · 반납 어디가 여유로워?"
          aria-label="자전거 도우미 질문"
        />
        <button className="btn primary" onClick={() => ask(q)} disabled={loading || !cutoff}>
          {loading ? "…" : "물어보기"}
        </button>
      </div>

      <div className="copilot-chips">
        {COPILOT_CHIPS.map((c) => (
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
          <p className="answer-text">{res.answer}</p>
          {res.stations.length > 0 && (
            <div className="station-list" style={{ marginTop: 10 }}>
              {res.stations.map((s) => (
                <StationRow key={s.station_id} s={s} onOpen={() => onOpen(s.station_id)} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Trip planner: "A에서 B까지" → walk → rent → bike → return → walk. All numbers (stations,
// distances, times) come from the deterministic /v2/rider/plan-trip; the LLM's role is only to parse
// the request + narrate (rule-based here, no key). Honest: straight-line distances, as-of inventory.
function TripPlanner({ cutoff }: { cutoff: string | null }) {
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState<TripPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function go(text: string) {
    if (!text.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      setPlan(await api.planTrip({ query: text, cutoff: cutoff ?? undefined }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card copilot">
      <h2>🧭 어디서 어디까지 — 길찾기</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        출발지와 목적지를 말하면 <strong>어디서 빌리고 · 어디에 반납하고 · 얼마나 걷는지</strong>를
        알려드려요. 예: “시청에서 뉴포트 가고 싶어”.
      </p>
      <div className="copilot-input">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && go(q)}
          placeholder="예: 시청에서 뉴포트 가고 싶어"
          aria-label="길찾기 질문"
        />
        <button onClick={() => go(q)} disabled={busy}>
          {busy ? "…" : "길찾기"}
        </button>
      </div>
      <div className="copilot-chips">
        {["시청에서 뉴포트", "그로브에서 익스체인지", "호보켄에서 시청"].map((c) => (
          <button key={c} className="chip" onClick={() => { setQ(c); go(c); }}>
            {c}
          </button>
        ))}
      </div>
      {err && <div className="copilot-answer unsupported">오류: {err}</div>}
      {plan && !plan.feasible && (
        <div className="copilot-answer unsupported">{plan.answer}</div>
      )}
      {plan && plan.feasible && (
        <div className="trip-plan" style={{ marginTop: 12 }}>
          <div className="copilot-answer">{plan.answer}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
            {plan.segments?.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 18 }}>{s.kind === "walk" ? "🚶" : "🚲"}</span>
                <span className="mono" style={{ minWidth: 92 }}>
                  {s.kind === "walk" ? "걷기" : "자전거"} {s.minutes}분
                </span>
                <span className="muted" style={{ fontSize: 13 }}>
                  {s.from} → {s.to} · {s.distance_m}m
                </span>
              </div>
            ))}
          </div>
          <div className="muted mono" style={{ fontSize: 12, marginTop: 10 }}>
            대여: {plan.rent_station?.ko} ({plan.rent_station?.bikes}대) · 반납: {plan.return_station?.ko} (
            {plan.return_station?.docks_free}칸) · 총 {plan.total_minutes}분
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{plan.disclaimer}</div>
        </div>
      )}
    </div>
  );
}

export default function RiderHome() {
  const router = useRouter();
  const { state, refreshKey, setSelectedZone } = useReplay();
  const cutoff = state?.cutoff ?? null;

  const search = useApi<StationSearchResponse>(
    () => api.stationSearch("", 50),
    [refreshKey, cutoff],
  );
  const ev = useApi<{ events: EventOut[] }>(() => api.events(), [refreshKey]);

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [view, setView] = useState<"list" | "map">("list");

  const allStations = useMemo(() => search.data?.stations ?? [], [search.data]);

  const counts = useMemo(() => {
    const c = { plenty: 0, ok: 0, tight: 0, low: 0 };
    for (const s of allStations) c[s.level] += 1;
    return c;
  }, [allStations]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return allStations.filter((s) => {
      if (filter === "good" && !(s.level === "plenty" || s.level === "ok")) return false;
      if (filter === "low" && !(s.level === "low" || s.level === "tight")) return false;
      if (!q) return true;
      return (
        s.ko.toLowerCase().includes(q) ||
        s.en.toLowerCase().includes(q) ||
        s.area.toLowerCase().includes(q) ||
        s.station_id.toLowerCase().includes(q)
      );
    });
  }, [allStations, query, filter]);

  const open = allStations.find((s) => s.station_id === openId) ?? null;
  const goToWhy = (zoneId: string) => {
    setSelectedZone(zoneId);
    router.push("/why");
  };

  if (search.error) {
    return (
      <div className="notice error">
        API에 연결할 수 없습니다 ({search.error}). <span className="mono">make api</span> 로 먼저 실행하세요.
      </div>
    );
  }

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="hero">
        <h1>내 주변 자전거 찾기</h1>
        <p className="muted">
          지역 이름으로 검색하고, 지금 빌리기 좋은 곳을 한눈에 확인하세요. 이벤트(교통장애·행사)로 수요가
          몰리는 지역도 함께 알려드려요.
        </p>
      </div>

      {/* Natural-language copilot (deterministic, tool-grounded) */}
      <RiderCopilot cutoff={cutoff} onOpen={(id) => setOpenId(id)} />

      {/* Trip planner: walk → rent → bike → return → walk (deterministic; LLM parses/narrates only) */}
      <TripPlanner cutoff={cutoff} />

      {/* Pull the latest news that could affect nearby availability */}
      <NewsSync compact />

      {/* Search bar — bike-share app style */}
      <div className="searchbar">
        <span className="search-icon" aria-hidden="true">🔍</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="지역 검색 — 예: 시청, 호보켄, Grove, 뉴포트"
          aria-label="자전거 대여소 검색"
        />
        {query && (
          <button className="search-clear" onClick={() => setQuery("")} aria-label="검색어 지우기">
            ✕
          </button>
        )}
      </div>

      {/* Availability summary + filter chips */}
      <div className="chips-row">
        <button
          className={`chip ${filter === "all" ? "active" : ""}`}
          onClick={() => setFilter("all")}
        >
          전체 {allStations.length}
        </button>
        <button
          className={`chip good ${filter === "good" ? "active" : ""}`}
          onClick={() => setFilter("good")}
        >
          빌리기 좋아요 {counts.plenty + counts.ok}
        </button>
        <button
          className={`chip low ${filter === "low" ? "active" : ""}`}
          onClick={() => setFilter("low")}
        >
          곧 부족 {counts.low + counts.tight}
        </button>

        {/* List / map view toggle */}
        <div className="view-toggle" role="tablist" aria-label="보기 방식">
          <button
            role="tab"
            aria-selected={view === "list"}
            className={view === "list" ? "active" : ""}
            onClick={() => setView("list")}
          >
            ☰ 목록
          </button>
          <button
            role="tab"
            aria-selected={view === "map"}
            className={view === "map" ? "active" : ""}
            onClick={() => setView("map")}
          >
            🗺 지도
          </button>
        </div>
      </div>

      {search.loading && !search.data ? (
        <div className="notice">주변 자전거 현황을 불러오는 중…</div>
      ) : filtered.length === 0 ? (
        <div className="notice">
          {query ? (
            <>
              ‘<strong>{query}</strong>’에 해당하는 대여소를 찾지 못했어요. 다른 이름으로 검색해 보세요.
            </>
          ) : (
            "조건에 맞는 대여소가 없어요."
          )}
        </div>
      ) : view === "map" ? (
        <StationMap stations={filtered} onOpen={(id) => setOpenId(id)} />
      ) : (
        <div className="station-list">
          {filtered.map((s) => (
            <StationRow key={s.station_id} s={s} onOpen={() => setOpenId(s.station_id)} />
          ))}
        </div>
      )}

      {ev.data?.events && ev.data.events.length > 0 && (
        <div className="card">
          <h2>지금 영향을 주는 이벤트</h2>
          <div className="sub">현재 재생 시각 기준으로 공개된 사건만 표시합니다.</div>
          <div className="grid" style={{ gap: 10 }}>
            {ev.data.events.map((e) => (
              <div key={e.event_id} className="event-line">
                <span className={`pill ${e.demand_effect}`}>
                  {e.demand_effect === "increase"
                    ? "수요 증가"
                    : e.demand_effect === "decrease"
                      ? "수요 감소"
                      : "영향 불명"}
                </span>
                <div>
                  <strong>{e.event_title}</strong>
                  <div className="muted small">
                    {e.locations.map((l) => l.name).join(", ") || e.event_type}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {open && (
        <StationSheet
          s={open}
          onClose={() => setOpenId(null)}
          onWhy={() => {
            setOpenId(null);
            goToWhy(open.zone_id);
          }}
        />
      )}
    </div>
  );
}
