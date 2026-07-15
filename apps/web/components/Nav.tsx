"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRole } from "@/app/role";

// Operator tools. In rider mode these are hidden entirely (clean consumer view); the rider only
// ever sees the home screen plus, when drilled into "why is this busy?", a back link.
const OPERATOR_TABS = [
  { href: "/statistics", label: "운영 통계" },
  { href: "/why", label: "수요 급증 원인" },
  { href: "/news", label: "뉴스 검색" },
  { href: "/scenario", label: "시나리오 비교" },
  { href: "/rebalancing", label: "재배치 계획" },
  { href: "/model-lift", label: "모델 Lift" },
  { href: "/anomaly", label: "이상 탐지" },
  { href: "/experiment", label: "실험 랩" },
];

export function Nav() {
  const path = usePathname();
  const { role } = useRole();

  if (role === "rider") {
    // Consumer view: no operator tab bar. Offer a way back from a drill-in detail page.
    if (path === "/") return null;
    return (
      <nav className="tabs">
        <Link href="/" className="rider-back">
          ← 자전거 찾기
        </Link>
      </nav>
    );
  }

  return (
    <nav className="tabs">
      {OPERATOR_TABS.map((t) => (
        <Link key={t.href} href={t.href} className={path === t.href ? "active" : ""}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
