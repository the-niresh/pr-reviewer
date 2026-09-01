"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { useDashboardSession } from "@/components/DashboardShell";
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
    return <p data-testid="dashboard-loading">Loading</p>;
  }

  if (findings.length === 0) {
    return <p data-testid="dashboard-empty">No findings for this job</p>;
  }

  return (
    <main>
      {costFailed ? <p data-testid="dashboard-partial-failure">Costs could not be loaded</p> : null}
      <section data-testid="finding-detail">
        {findings.map((item) => (
          <article key={item.id}>
            <h2>{item.title}</h2>
            <p>{item.status}</p>
          </article>
        ))}
      </section>
      <section data-testid="retrieved-context">
        {events.map((item, index) => (
          <p key={`${item.snippet ?? "event"}-${index}`}>{item.snippet}</p>
        ))}
      </section>
      {costs ? <p data-testid="job-costs">{costs.cost_usd}</p> : null}
      <section data-testid="workflow-trace">
        {segments.map((segment, index) => (
          <p key={`${segment.origin}-${segment.kind}-${index}`}>
            {segment.origin} {segment.kind}
          </p>
        ))}
      </section>
    </main>
  );
}
