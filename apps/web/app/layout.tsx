import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Noto_Sans_KR } from "next/font/google";
import { ReplayProvider } from "./providers";
import { Nav } from "@/components/Nav";
import { ReplayControl } from "@/components/ReplayControl";

// Korean-first gothic for readability. Self-hosted by next/font at build time (offline at
// runtime); the CSS stack in globals.css falls back to the platform gothic
// (Apple SD Gothic Neo / Malgun Gothic) if this is ever unavailable.
const notoSansKr = Noto_Sans_KR({
  subsets: ["latin"],
  weight: ["400", "500", "700", "800"],
  display: "swap",
  variable: "--font-noto-sans-kr",
});

export const metadata: Metadata = {
  title: "ShockFlow AI — 자전거 수요 예보",
  description:
    "이벤트를 반영한 지역별 자전거 수요·재고 예보. 어느 지역에 자전거가 많을지 미리 확인하세요 (오프라인 데모).",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" className={notoSansKr.variable}>
      <body>
        <ReplayProvider>
          <header className="topbar">
            <span className="brand">
              ShockFlow AI <small>자전거 수요 예보</small>
            </span>
            <Nav />
          </header>
          <div className="container">
            <div className="card" style={{ marginBottom: 16 }}>
              <ReplayControl />
            </div>
            {children}
            <p className="footer-note">
              과거 재생(Historical Replay) 데모입니다. 예보는 측정된 Phase 06 모델이 아니라
              라벨이 붙은 데모 heuristic(<span className="mono">demo-heuristic-v1</span>)에서 나오며,
              이벤트로 인한 수요 변화(Δ)는 그래프 이벤트 노출 지표를 그대로 반영한 값입니다.
              실제 서비스 데이터가 아닌 오프라인 뉴스·재고 fixture로 완전히 동작합니다.
            </p>
          </div>
        </ReplayProvider>
      </body>
    </html>
  );
}
