"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { dashboardGet } from "@/lib/dashboardApi";

type SessionState = {
  csrf: string;
  runnerId: string;
  ready: boolean;
};

const NAV = [
  { href: "/dashboard/reviews", label: "Reviews" },
  { href: "/dashboard", label: "Approvals" },
  { href: "/dashboard/evals", label: "Evals" },
  { href: "/dashboard/connectors", label: "Connectors" },
] as const;

const SessionContext = createContext<SessionState>({ csrf: "", runnerId: "", ready: false });

export function useDashboardSession(): SessionState {
  return useContext(SessionContext);
}

export function DashboardShell({ children }: { children: ReactNode }) {
  const [csrf, setCsrf] = useState("");
  const [runnerId, setRunnerId] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const sessionResponse = await dashboardGet("/dashboard/session");
      if (!sessionResponse.ok) {
        return;
      }
      const session = (await sessionResponse.json()) as { csrf_token: string };
      const accountResponse = await dashboardGet("/dashboard/account");
      if (!accountResponse.ok) {
        return;
      }
      const account = (await accountResponse.json()) as { runner_id: string };
      if (!cancelled) {
        setCsrf(session.csrf_token);
        setRunnerId(account.runner_id);
        setReady(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <SessionContext.Provider value={{ csrf, runnerId, ready }}>
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
          <p
            data-testid="dashboard-account"
            className="text-muted-foreground ml-auto font-mono text-xs"
          >
            {runnerId}
          </p>
        </div>
      </header>
      {children}
    </SessionContext.Provider>
  );
}
