"use client";

import { useReplay } from "@/app/providers";
import { ModeBadge } from "./ModeBadge";
import { fmtClock } from "@/lib/format";

// Golden-path cutoffs (section 7.2): the transit event crosses 13:59 -> 14:00.
const PRESETS: { label: string; iso: string }[] = [
  { label: "13:59 · before", iso: "2026-07-12T13:59:00-04:00" },
  { label: "14:00 · transit", iso: "2026-07-12T14:00:00-04:00" },
  { label: "14:30", iso: "2026-07-12T14:30:00-04:00" },
  { label: "15:30 · concert", iso: "2026-07-12T15:30:00-04:00" },
  { label: "18:00 · end", iso: "2026-07-12T18:00:00-04:00" },
];

const STEP_MIN = 30;

export function ReplayControl() {
  const { state, error, setCutoff } = useReplay();

  if (error && !state) {
    return (
      <div className="notice error">
        API unreachable ({error}). Start it with <span className="mono">make api</span>.
      </div>
    );
  }
  if (!state) return <div className="notice">Loading replay clock…</div>;

  const start = new Date(state.window_start).getTime();
  const end = new Date(state.window_end).getTime();
  const cur = new Date(state.cutoff).getTime();
  const steps = Math.round((end - start) / (STEP_MIN * 60000));
  const curStep = Math.round((cur - start) / (STEP_MIN * 60000));

  return (
    <div className="replay-bar">
      <ModeBadge mode={state.mode} />
      <span className="clock mono">⏱ {fmtClock(state.cutoff)}</span>
      <span className="muted">
        {state.available_event_count} event{state.available_event_count === 1 ? "" : "s"} available
      </span>
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
        aria-label="Replay cutoff"
        onChange={(e) => {
          const ms = start + Number(e.target.value) * STEP_MIN * 60000;
          void setCutoff(new Date(ms).toISOString());
        }}
        style={{ minWidth: 180, flex: 1 }}
      />
    </div>
  );
}
