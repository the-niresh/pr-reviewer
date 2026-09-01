export const DASHBOARD_API =
  process.env.NEXT_PUBLIC_DASHBOARD_API_ORIGIN ?? "http://127.0.0.1:8742";

export type JobItem = {
  job_id: string;
  runner_id: string;
  repository_id: number;
  status: string;
};

export type FindingItem = {
  id: string;
  review_job_id: string;
  title: string;
  status: string;
};

export type CostItem = {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
};

export type TraceSegment = {
  origin: string;
  kind: string;
};

export type EvalItem = {
  id: string;
  reason?: string;
  blocked?: boolean;
  baseline?: string;
  candidate?: string;
};

export async function dashboardGet(path: string): Promise<Response> {
  return fetch(`${DASHBOARD_API}${path}`, { credentials: "include" });
}

export async function dashboardPost(
  path: string,
  csrf: string,
  body: unknown,
): Promise<Response> {
  return fetch(`${DASHBOARD_API}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
    },
    body: JSON.stringify(body),
  });
}
