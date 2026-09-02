"use client";

import { useEffect, useState } from "react";

import { useDashboardSession } from "@/components/DashboardShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    return (
      <p data-testid="dashboard-loading" className="text-muted-foreground px-6 py-16 text-sm">
        Loading
      </p>
    );
  }

  return (
    <main data-testid="eval-comparison" className="mx-auto w-full max-w-3xl px-6 py-10">
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">Evals</h1>
      <div className="flex flex-col gap-4">
        {items.map((item) => (
          <Card key={item.id}>
            <CardHeader>
              <CardTitle className="font-mono">{item.id}</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground text-xs tracking-[0.14em] uppercase">
                    Baseline
                  </dt>
                  <dd className="mt-1 text-sm">{item.baseline}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground text-xs tracking-[0.14em] uppercase">
                    Candidate
                  </dt>
                  <dd className="mt-1 text-sm">{item.candidate}</dd>
                </div>
              </dl>
              <p className="text-muted-foreground mt-4 border-t pt-3 text-sm">{item.reason}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
