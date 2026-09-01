"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { dashboardGet } from "@/lib/dashboardApi";

type SessionState = {
  csrf: string;
  runnerId: string;
  ready: boolean;
};

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
      <header>
        <p data-testid="dashboard-account">{runnerId}</p>
        <nav>
          <Link href="/dashboard">Approvals</Link>
          <Link href="/dashboard/evals">Evals</Link>
          <Link href="/dashboard/connectors">Connectors</Link>
        </nav>
      </header>
      {children}
    </SessionContext.Provider>
  );
}
