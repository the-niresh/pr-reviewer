"use client";

import { useEffect, useState } from "react";

import { useDashboardSession } from "@/components/DashboardShell";
import { dashboardGet } from "@/lib/dashboardApi";

export default function ConnectorsPage() {
  const { ready } = useDashboardSession();
  const [status, setStatus] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    async function load() {
      const response = await dashboardGet("/dashboard/connectors");
      if (!response.ok || cancelled) {
        return;
      }
      setStatus((await response.json()) as Record<string, string>);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [ready]);

  if (status === null) {
    return <p data-testid="dashboard-loading">Loading</p>;
  }

  return (
    <main data-testid="connector-status">
      {Object.entries(status).map(([name, value]) => (
        <p key={name}>
          {name} {value}
        </p>
      ))}
    </main>
  );
}
