"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Control Tower" },
  { href: "/why", label: "Why Changed" },
  { href: "/scenario", label: "Scenario Lab" },
  { href: "/rebalancing", label: "Rebalancing" },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="tabs">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} className={path === t.href ? "active" : ""}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
