"use client";

import { useReplay } from "@/app/providers";
import { ModeBadge } from "./ModeBadge";
import { fmtClock } from "@/lib/format";

// Rider-mode replay indicator: read-only. Riders see the mode + as-of time honestly (never
// fixture-as-live), but the replay scrubber/presets are an operator control and stay hidden here.
export function RiderClock() {
  const { state, error } = useReplay();

  if (error && !state) {
    return (
      <div className="notice error">
        API에 연결할 수 없습니다 ({error}). <span className="mono">make api</span> 로 먼저 실행하세요.
      </div>
    );
  }
  if (!state) return <div className="notice">현재 상태를 불러오는 중…</div>;

  return (
    <div className="replay-bar">
      <ModeBadge mode={state.mode} />
      <span className="clock mono">⏱ {fmtClock(state.cutoff)} 기준</span>
      <span className="muted">이벤트 {state.available_event_count}건 반영</span>
    </div>
  );
}
