"use client";

import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Ask" },
  { href: "/how-it-works/", label: "How it works" },
  { href: "/faq/", label: "FAQ" },
  { href: "/results/", label: "Evaluation results" },
];

export default function SiteHeader() {
  const path = usePathname() || "/";
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <a className="brand" href="/">
          <svg className="logo" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <rect x="1" y="1" width="26" height="26" rx="7" fill="none" stroke="currentColor" strokeWidth="2" />
            <circle cx="9" cy="14" r="2.5" fill="currentColor" />
            <circle cx="19" cy="9" r="2.5" fill="currentColor" />
            <circle cx="19" cy="19" r="2.5" fill="currentColor" />
            <path d="M11 13 L17 10 M11 15 L17 18" stroke="currentColor" strokeWidth="1.6" />
          </svg>
          <span>Service Ops Intelligence</span>
        </a>
        <nav aria-label="Main" className="nav">
          {LINKS.map(({ href, label }) => {
            const here = href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
            return (
              <a key={href} href={href} aria-current={here ? "page" : undefined}>
                {label}
              </a>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
