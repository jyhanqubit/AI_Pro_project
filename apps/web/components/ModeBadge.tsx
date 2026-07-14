import type { OperatingMode } from "@/lib/api";

const LABELS: Record<OperatingMode, string> = {
  demo_fixture: "데모 재생",
  historical_replay: "과거 재생",
  live: "실시간",
  research: "연구",
};

// Historical Replay and Live must be visually distinct (section 13).
export function ModeBadge({ mode }: { mode: OperatingMode }) {
  const cls = mode === "live" ? "live" : "replay";
  return (
    <span className={`badge ${cls}`} title={`운영 모드: ${LABELS[mode]}`}>
      <span className="dot" />
      {LABELS[mode]}
    </span>
  );
}
