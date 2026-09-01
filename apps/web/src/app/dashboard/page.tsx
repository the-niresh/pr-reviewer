"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useDashboardSession } from "@/components/DashboardShell";
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
    return <p data-testid="dashboard-permission-denied">Permission denied</p>;
  }

  if (loading || !ready || approvals === null) {
    return <p data-testid="dashboard-loading">Loading</p>;
  }

  return (
    <main>
      <h1>Approvals</h1>
      <button type="button" onClick={() => void load(true)}>
        Refresh
      </button>
      {stale ? <p data-testid="dashboard-stale">Showing last loaded queue</p> : null}
      <ul data-testid="approval-queue">
        {approvals.map((item) => (
          <li key={item.id}>
            <span>{item.title}</span>
            <button type="button" onClick={() => void decide(item, "approved")}>
              Approve {item.title}
            </button>
            <button type="button" onClick={() => void decide(item, "rejected")}>
              Reject {item.title}
            </button>
          </li>
        ))}
      </ul>
      <ul data-testid="job-list">
        {jobs.map((job) => (
          <li key={job.job_id}>
            <Link href={`/dashboard/jobs/${job.job_id}`}>{job.job_id}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
