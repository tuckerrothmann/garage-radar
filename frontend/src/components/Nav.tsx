"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const links = [
  { href: "/",        label: "Listings" },
  { href: "/alerts",  label: "Alerts"   },
  { href: "/comps",   label: "Comp Clusters" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="bg-radar-card border-b border-radar-border">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-8">
        <span className="font-bold text-radar-red tracking-tight text-lg select-none">
          🏎 Garage Radar
        </span>
        <nav className="flex gap-1">
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "px-3 py-1.5 rounded text-sm font-medium transition-colors",
                path === href
                  ? "bg-radar-border text-white"
                  : "text-radar-muted hover:text-white hover:bg-radar-border/50",
              )}
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
