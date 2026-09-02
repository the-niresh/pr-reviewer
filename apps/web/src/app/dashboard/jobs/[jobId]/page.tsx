"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { useDashboardSession } from "@/components/DashboardShell";
import { Badge } from "@/components/ui/badge";
import {
  dashboardGet,
  type CostItem,
  type FindingItem,
  type TraceSegment,
} from "@/lib/dashboardApi";

type ContextEvent = {
  type?: string;
  snippet?: string;
};

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { ready } = useDashboardSession();
  const [findings, setFindings] = useState<FindingItem[] | null>(null);
  const [events, setEvents] = useState<ContextEvent[]>([]);
  const [costs, setCosts] = useState<CostItem | null>(null);
  const [segments, setSegments] = useState<TraceSegment[]>([]);
  const [costFailed, setCostFailed] = useState(false);

  useEffect(() => {
    if (!ready || !jobId) {
      return;
    }
    let cancelled = false;
    async function load() {
      const [findingResponse, eventResponse, costResponse, traceResponse] = await Promise.all([
        dashboardGet(`/dashboard/jobs/${jobId}/findings`),
        dashboardGet(`/dashboard/jobs/${jobId}/events`),
        dashboardGet(`/dashboard/jobs/${jobId}/costs`),
        dashboardGet(`/dashboard/jobs/${jobId}/trace`),
      ]);
      if (cancelled) {
        return;
      }
      if (findingResponse.ok) {
        const body = (await findingResponse.json()) as { items: FindingItem[] };
        setFindings(body.items);
      } else {
        setFindings([]);
      }
      if (eventResponse.ok) {
        const body = (await eventResponse.json()) as { items: ContextEvent[] };
        setEvents(body.items);
      }
      if (costResponse.ok) {
        setCosts((await costResponse.json()) as CostItem);
        setCostFailed(false);
      } else {
        setCostFailed(true);
      }
      if (traceResponse.ok) {
        const body = (await traceResponse.json()) as { segments: TraceSegment[] };
        setSegments(body.segments);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [ready, jobId]);

  if (findings === null) {
    return (
      <p data-testid="dashboard-loading" className="text-muted-foreground px-6 py-16 text-sm">
        Loading
      </p>
    );
  }

  if (findings.length === 0) {
    return (
      <p data-testid="dashboard-empty" className="text-muted-foreground px-6 py-16 text-sm">
        No findings for this job
      </p>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-mono text-lg font-semibold tracking-tight">{jobId}</h1>
        {costs ? (
          <p data-testid="job-costs" className="font-mono text-sm tabular-nums">
            {costs.cost_usd}
          </p>
        ) : null}
      </div>

      {costFailed ? (
        <p
          data-testid="dashboard-partial-failure"
          className="border-[var(--warning)]/40 bg-[var(--warning)]/10 text-[var(--warning)] mb-6 rounded-md border px-3 py-2 text-sm"
        >
          Costs could not be loaded
        </p>
      ) : null}

      <section data-testid="finding-detail" className="flex flex-col gap-2">
        {findings.map((item) => (
          <article
            key={item.id}
            className="bg-card flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3"
          >
            <h2 className="min-w-0 flex-1 text-sm font-medium">{item.title}</h2>
            <Badge variant={item.status === "posted" ? "default" : "muted"}>
              {item.status}
            </Badge>
          </article>
        ))}
      </section>

      <h2 className="text-muted-foreground mt-10 mb-3 text-xs font-medium tracking-[0.14em] uppercase">
        Retrieved context
      </h2>
      <section data-testid="retrieved-context" className="flex flex-col gap-1.5">
        {events.map((item, index) => (
          <p
            key={`${item.snippet ?? "event"}-${index}`}
            className="bg-muted/40 rounded-md px-3 py-2 font-mono text-xs"
          >
            {item.snippet}
          </p>
        ))}
      </section>

      <h2 className="text-muted-foreground mt-10 mb-3 text-xs font-medium tracking-[0.14em] uppercase">
        Workflow trace
      </h2>
      <section data-testid="workflow-trace" className="flex flex-col gap-px overflow-hidden rounded-lg border">
        {segments.map((segment, index) => (
          <p
            key={`${segment.origin}-${segment.kind}-${index}`}
            className="bg-card flex items-center gap-3 px-4 py-2 font-mono text-xs"
          >
            <span className="text-primary">{segment.origin}</span>
            <span className="text-muted-foreground">{segment.kind}</span>
          </p>
        ))}
      </section>
    </main>
  );
}
