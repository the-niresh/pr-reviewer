"use client";

import { useEffect, useState } from "react";

import { useDashboardSession } from "@/components/DashboardShell";
import { Badge } from "@/components/ui/badge";
import { dashboardGet } from "@/lib/dashboardApi";

/** A connector that is open or failing must not read as the brand accent. */
function statusTone(value: string): "default" | "warning" | "danger" | "muted" {
  const v = value.toLowerCase();
  if (v.includes("closed") || v.includes("ok") || v.includes("health")) return "default";
  if (v.includes("open") || v.includes("fail") || v.includes("error")) return "danger";
  if (v.includes("half") || v.includes("degrad")) return "warning";
  return "muted";
}

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
    return (
      <p data-testid="dashboard-loading" className="text-muted-foreground px-6 py-16 text-sm">
        Loading
      </p>
    );
  }

  return (
    <main data-testid="connector-status" className="mx-auto w-full max-w-3xl px-6 py-10">
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Connectors</h1>
      <dl className="overflow-hidden rounded-lg border">
        {Object.entries(status).map(([name, value]) => (
          <div
            key={name}
            className="bg-card flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0"
          >
            <dt className="font-mono text-sm">{name}</dt>
            <dd>
              <Badge variant={statusTone(value)}>{value}</Badge>
            </dd>
          </div>
        ))}
      </dl>
    </main>
  );
}
