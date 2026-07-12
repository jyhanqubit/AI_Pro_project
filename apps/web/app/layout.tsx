import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ReplayProvider } from "./providers";
import { Nav } from "@/components/Nav";
import { ReplayControl } from "@/components/ReplayControl";

export const metadata: Metadata = {
  title: "ShockFlow AI — Operator Console",
  description:
    "Event-aware demand forecasting & rebalancing decision support (Phase 07, offline demo).",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ReplayProvider>
          <header className="topbar">
            <span className="brand">
              ShockFlow AI <small>Operator Console</small>
            </span>
            <Nav />
          </header>
          <div className="container">
            <div className="card" style={{ marginBottom: 16 }}>
              <ReplayControl />
            </div>
            {children}
            <p className="footer-note">
              Historical Replay demo — forecasts come from a labelled demo heuristic
              (<span className="mono">demo-heuristic-v1</span>), not the measured Phase 06 model.
              The event-aware delta is a transparent function of the graph event-exposure feature.
              Runs fully offline from the news fixture.
            </p>
          </div>
        </ReplayProvider>
      </body>
    </html>
  );
}
