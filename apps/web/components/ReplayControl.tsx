"use client";

import { useReplay } from "@/app/providers";
import { ModeBadge } from "./ModeBadge";
import { fmtClock } from "@/lib/format";

// Golden-path cutoffs (section 7.2): the transit event crosses 13:59 -> 14:00.
const PRESETS: { label: string; iso: string }[] = [
  { label: "13:59 · 이벤트 전", iso: "2026-07-12T13:59:00-04:00" },
  { label: "14:00 · 교통장애", iso: "2026-07-12T14:00:00-04:00" },
  { label: "14:30", iso: "2026-07-12T14:30:00-04:00" },
  { label: "15:30 · 콘서트", iso: "2026-07-12T15:30:00-04:00" },
  { label: "18:00 · 종료", iso: "2026-07-12T18:00:00-04:00" },
];

const STEP_MIN = 30;

export function ReplayControl() {
  const { state, error, setCutoff } = useReplay();

  if (error && !state) {
    return (
      <div className="notice error">
        API에 연결할 수 없습니다 ({error}). <span className="mono">make api</span> 로 먼저 실행하세요.
      </div>
    );
  }
  if (!state) return <div className="notice">재생 시계를 불러오는 중…</div>;

  const start = new Date(state.window_start).getTime();
  const end = new Date(state.window_end).getTime();
  const cur = new Date(state.cutoff).getTime();
  const steps = Math.round((end - start) / (STEP_MIN * 60000));
  const curStep = Math.round((cur - start) / (STEP_MIN * 60000));

  return (
    <div className="replay-bar">
      <ModeBadge mode={state.mode} />
      <span className="clock mono">⏱ {fmtClock(state.cutoff)} 기준</span>
      <span className="muted">이벤트 {state.available_event_count}건 반영됨</span>
      <div className="presets">
        {PRESETS.map((p) => (
          <button key={p.iso} onClick={() => void setCutoff(p.iso)}>
            {p.label}
          </button>
        ))}
      </div>
      <input
        type="range"
        min={0}
        max={steps}
        value={curStep}
        step={1}
        aria-label="재생 시각"
        onChange={(e) => {
          const ms = start + Number(e.target.value) * STEP_MIN * 60000;
          void setCutoff(new Date(ms).toISOString());
        }}
        style={{ minWidth: 180, flex: 1 }}
      />
    </div>
  );
}
