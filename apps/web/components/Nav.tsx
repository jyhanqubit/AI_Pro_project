"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Rider-facing home first, then the operator tools.
const RIDER_TABS = [{ href: "/", label: "자전거 찾기" }];
const OPERATOR_TABS = [
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
  const link = (t: { href: string; label: string }) => (
    <Link key={t.href} href={t.href} className={path === t.href ? "active" : ""}>
      {t.label}
    </Link>
  );
  return (
    <nav className="tabs">
      {RIDER_TABS.map(link)}
      <span className="tabs-divider" aria-hidden="true" />
      <span className="tabs-group-label">운영자</span>
      {OPERATOR_TABS.map(link)}
    </nav>
  );
}
