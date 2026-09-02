"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// Approvals, Evals and Connectors used to live here too, each reading a session from the
// local runner's own loopback API. They moved to the runner's own web surface (task
// 33.C5): a hosted https origin can never reach a loopback address on the viewer's
// machine, which is why those pages hung on "Loading" forever. Everything under
// /dashboard needs none of that -- it reads the viewer's GitHub sign-in cookie and calls
// the hosted control plane -- so this shell is a plain nav with nothing of its own to fetch.
const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/dashboard/reviews", label: "Reviews" },
  { href: "/dashboard/profile", label: "Profile" },
  { href: "/dashboard/settings", label: "Settings" },
] as const;

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
          <nav aria-label="Dashboard" className="flex items-center gap-1">
            {NAV.map((item) => {
              // "/dashboard" itself must not stay lit for every nested route under it, so
              // it gets an exact match while the rest also match their own subpaths (a
              // single review page under /dashboard/reviews/[id] still shows "Reviews" as
              // current).
              const isCurrent =
                item.href === "/dashboard"
                  ? pathname === item.href
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={isCurrent ? "page" : undefined}
                  className="text-muted-foreground hover:text-foreground hover:bg-secondary aria-[current=page]:bg-secondary aria-[current=page]:text-foreground rounded-md px-3 py-1.5 text-sm font-medium transition-colors aria-[current=page]:font-semibold focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      {children}
    </>
  );
}
