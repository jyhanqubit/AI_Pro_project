"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useReplay } from "./providers";
import { useApi } from "@/lib/useApi";
import {
  api,
  type AvailabilityLevel,
  type EventOut,
  type StationHit,
  type StationSearchResponse,
} from "@/lib/api";
import { signed } from "@/lib/format";
import { StationMap } from "@/components/StationMap";

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
