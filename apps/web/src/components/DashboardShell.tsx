import Link from "next/link";
import type { ReactNode } from "react";

// Approvals, Evals and Connectors used to live here too, each reading a session from the
// local runner's own loopback API. They moved to the runner's own web surface (task
// 33.C5): a hosted https origin can never reach a loopback address on the viewer's
// machine, which is why those pages hung on "Loading" forever. /dashboard/reviews needs
// none of that - it reads the viewer's GitHub sign-in cookie and calls the hosted control
// plane - so this shell is back to being a plain nav with nothing to fetch.
const NAV = [{ href: "/dashboard/reviews", label: "Reviews" }] as const;

export function DashboardShell({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
          <nav aria-label="Dashboard" className="flex items-center gap-1">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md px-3 py-1.5 text-sm transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      {children}
    </>
  );
}
