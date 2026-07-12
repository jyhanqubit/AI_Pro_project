"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

// Rebalancing is implemented in Phase 08. This screen is honest about that: it calls the API and
// surfaces the 501, and describes the planned solver ladder — no fabricated plan (sections 13, 22).
export default function RebalancingPlanner() {
  const [status, setStatus] = useState<string>("checking…");

  useEffect(() => {
    fetch(`${API_BASE}/v1/rebalancing/solve`, { method: "POST" })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        setStatus(`API ${r.status}: ${body?.detail?.message ?? r.statusText}`);
      })
      .catch((e) => setStatus(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="card">
        <h2>Rebalancing Planner</h2>
        <div className="sub">Turn the forecast into a feasible relocation plan.</div>
        <div className="notice info">
          Planned for <strong>Phase 08</strong> — not yet implemented, and deliberately not faked.
          <br />
          <span className="mono">{status}</span>
        </div>
      </div>

      <div className="card">
        <h2>Planned solver ladder (Phase 08)</h2>
        <div className="sub">Classical first, then a small quantum research track.</div>
        <ol style={{ lineHeight: 1.8, margin: 0, paddingLeft: 20 }}>
          <li>Greedy feasible baseline (move surplus toward shortage within capacity).</li>
          <li>Classical MILP: shortage + overflow + relocation-distance costs, capacity constraints.</li>
          <li>Small QUBO conversion, validated against exact enumeration.</li>
          <li>
            Optional QAOA simulator — <strong>Quantum Research Mode</strong>, never presented as
            hardware, no quantum-advantage claim.
          </li>
        </ol>
        <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
          Every plan will report origin, destination, moved quantity, distance/cost, and an
          explicit feasibility check before it is shown.
        </p>
      </div>
    </div>
  );
}
