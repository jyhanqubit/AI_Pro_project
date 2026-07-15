import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Noto_Sans_KR } from "next/font/google";
import { ReplayProvider } from "./providers";
import { RoleProvider } from "./role";
import { Nav } from "@/components/Nav";
import { RoleSwitch } from "@/components/RoleSwitch";
import { ReplayArea } from "@/components/ReplayArea";

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
          <RoleProvider>
            <header className="topbar">
              <span className="brand">
                ShockFlow AI <small>자전거 수요 예보</small>
              </span>
              <RoleSwitch />
              <Nav />
            </header>
            <div className="container">
              <ReplayArea />
              {children}
              <p className="footer-note">
                데모용 데이터입니다. 과거 재생(Historical Replay) 모드로, 예보는 데모용
                heuristic(<span className="mono">demo-heuristic-v1</span>)에서 나오며 수요 변화(Δ)는
                그래프 이벤트 노출 지표를 반영합니다. 뉴스 동기화 시 불러온 실시간 뉴스에는 LIVE 배지가
                붙습니다.
              </p>
            </div>
          </RoleProvider>
        </ReplayProvider>
      </body>
    </html>
  );
}
