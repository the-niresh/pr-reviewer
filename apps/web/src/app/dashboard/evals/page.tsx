"use client";

import { useEffect, useState } from "react";

import { useDashboardSession } from "@/components/DashboardShell";
import { dashboardGet, type EvalItem } from "@/lib/dashboardApi";

export default function EvalsPage() {
  const { ready } = useDashboardSession();
  const [items, setItems] = useState<EvalItem[] | null>(null);

  useEffect(() => {
    if (!ready) {
      return;
    }
    let cancelled = false;
    async function load() {
      const response = await dashboardGet("/dashboard/evals");
      if (!response.ok || cancelled) {
        return;
      }
      const body = (await response.json()) as { items: EvalItem[] };
      setItems(body.items);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [ready]);

  if (items === null) {
    return <p data-testid="dashboard-loading">Loading</p>;
  }

  return (
    <main data-testid="eval-comparison">
      {items.map((item) => (
        <article key={item.id}>
          <h2>{item.id}</h2>
          <p>{item.baseline}</p>
          <p>{item.candidate}</p>
          <p>{item.reason}</p>
        </article>
      ))}
    </main>
  );
}
