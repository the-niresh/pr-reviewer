"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { useDashboardSession } from "@/components/DashboardShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { dashboardGet, dashboardPost, type FindingItem, type JobItem } from "@/lib/dashboardApi";

export default function DashboardHomePage() {
  const { csrf, ready } = useDashboardSession();
  const [approvals, setApprovals] = useState<FindingItem[] | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [stale, setStale] = useState(false);

  const load = useCallback(async (keepExisting: boolean) => {
    if (!keepExisting) {
      setLoading(true);
    }
    const [approvalResponse, jobResponse] = await Promise.all([
      dashboardGet("/dashboard/approvals"),
      dashboardGet("/dashboard/jobs"),
    ]);
    if (approvalResponse.status === 401) {
      setDenied(true);
      setLoading(false);
      return;
    }
    if (!approvalResponse.ok) {
      if (keepExisting) {
        setStale(true);
      }
      setLoading(false);
      return;
    }
    const approvalBody = (await approvalResponse.json()) as { items: FindingItem[] };
    setApprovals(approvalBody.items);
    setDenied(false);
    setStale(false);
    if (jobResponse.ok) {
      const jobBody = (await jobResponse.json()) as { items: JobItem[] };
      setJobs(jobBody.items);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!ready) {
      return;
    }
    void load(false);
  }, [ready, load]);

  async function decide(finding: FindingItem, decision: "approved" | "rejected") {
    const response = await dashboardPost(`/dashboard/approvals/${finding.id}`, csrf, { decision });
    if (!response.ok) {
      return;
    }
    setApprovals((current) => (current ?? []).filter((item) => item.id !== finding.id));
  }

  if (denied) {
    return (
      <p
        data-testid="dashboard-permission-denied"
        className="text-muted-foreground px-6 py-16 text-sm"
      >
        Permission denied
      </p>
    );
  }

  if (loading || !ready || approvals === null) {
    return (
      <p data-testid="dashboard-loading" className="text-muted-foreground px-6 py-16 text-sm">
        Loading
      </p>
    );
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
          <Badge variant={approvals.length ? "default" : "muted"}>
            {approvals.length} waiting
          </Badge>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load(true)}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </Button>
      </div>

      {stale ? (
        <p
          data-testid="dashboard-stale"
          className="border-[var(--warning)]/40 bg-[var(--warning)]/10 text-[var(--warning)] mb-5 rounded-md border px-3 py-2 text-sm"
        >
          Showing last loaded queue
        </p>
      ) : null}

      <ul data-testid="approval-queue" className="flex flex-col gap-2">
        {approvals.map((item) => (
          <li
            key={item.id}
            className="bg-card flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3"
          >
            <span className="min-w-0 flex-1 text-sm">{item.title}</span>
            <div className="flex shrink-0 gap-2">
              <Button type="button" size="sm" onClick={() => void decide(item, "approved")}>
                Approve {item.title}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void decide(item, "rejected")}
              >
                Reject {item.title}
              </Button>
            </div>
          </li>
        ))}
      </ul>

      <Card className="mt-10">
        <CardHeader>
          <CardTitle>Jobs</CardTitle>
        </CardHeader>
        <CardContent>
          <ul data-testid="job-list" className="flex flex-col gap-1">
            {jobs.map((job) => (
              <li key={job.job_id}>
                <Link
                  href={`/dashboard/jobs/${job.job_id}`}
                  className="text-primary rounded-sm font-mono text-sm underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  {job.job_id}
                </Link>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </main>
  );
}
