/** Shared shapes and fetch for the hosted control plane's /api/reviews surface. Every
 *  /dashboard/* page reads through fetchReviews so "not signed in", "could not load", and
 *  "loaded, and there is nothing here yet" stay three distinct, honest outcomes everywhere
 *  they are shown, instead of each page re-deriving its own guess at the difference. */

export const CONTROL_PLANE_ORIGIN =
  process.env.NEXT_PUBLIC_CONTROL_PLANE_ORIGIN ?? "http://127.0.0.1:8000";

export type ReceiptContextSource = {
  kind: string;
  name: string;
  reference: string;
};

export type FindingReceipt = {
  provider: string | null;
  model: string | null;
  cost_usd: string | null;
  verification_status: "verified" | "asserted";
  verification_reason: string | null;
  sandbox_run_id: string | null;
  verification_detail: string | null;
  context_sources: ReceiptContextSource[];
};

export type ReviewFinding = {
  id: string;
  concern: string;
  severity: string;
  category: string;
  file_path: string;
  line_start: number;
  line_end: number;
  title: string;
  rationale: string;
  verified: boolean;
  status: string;
  receipt: FindingReceipt | null;
};

export type ReviewSummary = {
  review_job_id: string;
  pull_request_number: number | null;
  head_sha: string | null;
  status: string;
  stopped_early: boolean;
  stopped_early_message: string | null;
  created_at: string;
  findings: ReviewFinding[];
};

export type RepositoryReviews = {
  installation_id: number;
  github_repository_id: number;
  repository_name: string;
  reviews: ReviewSummary[];
};

export type ReviewsResponse = {
  repositories: RepositoryReviews[];
};

export const SEVERITY_LEVELS = ["critical", "high", "medium", "low", "info"] as const;
export type SeverityLevel = (typeof SEVERITY_LEVELS)[number];

/** Severity is semantic and deliberately separate from the brand accent, so "critical"
 *  can never read as "this is fine, it is just our colour". */
export function severityTone(severity: string): "danger" | "warning" | "muted" {
  const level = severity.toLowerCase();
  if (level === "critical" || level === "high") return "danger";
  if (level === "medium") return "warning";
  return "muted";
}

const SEVERITY_RANK: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
  info: 0,
};

/** The single worst severity among a review's findings, or null when it has none. Used
 *  wherever a review needs to be summarised down to one severity, e.g. the reviews table. */
export function worstSeverity(findings: ReviewFinding[]): string | null {
  let worst: string | null = null;
  let worstRank = -1;
  for (const finding of findings) {
    const rank = SEVERITY_RANK[finding.severity.toLowerCase()] ?? 0;
    if (rank > worstRank) {
      worst = finding.severity;
      worstRank = rank;
    }
  }
  return worst;
}

export type FetchReviewsResult =
  | { kind: "unauthenticated" }
  | { kind: "error" }
  | { kind: "ok"; data: ReviewsResponse };

export type FetchReviewResult =
  | { kind: "unauthenticated" }
  | { kind: "not_found" }
  | { kind: "error" }
  | { kind: "ok"; review: ReviewSummary };

/** The one place that calls GET /api/reviews with the viewer's own session cookie. A
 *  network failure or a non-401 error status is reported as "error", never silently
 *  reshaped into an empty result: an empty dashboard and a broken one must never look
 *  the same. */
export async function fetchReviews(cookieHeader: string): Promise<FetchReviewsResult> {
  let response: Response;
  try {
    response = await fetch(`${CONTROL_PLANE_ORIGIN}/api/reviews`, {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
  } catch {
    return { kind: "error" };
  }
  if (response.status === 401) {
    return { kind: "unauthenticated" };
  }
  if (!response.ok) {
    return { kind: "error" };
  }
  const data = (await response.json()) as ReviewsResponse;
  return { kind: "ok", data };
}

/** Backs /dashboard/reviews/[reviewJobId]. 404 is a real, distinct outcome here (the review
 *  does not exist, or exists but belongs to a repository this viewer's installations do not
 *  grant -- the control plane collapses those on purpose), never folded into "error". */
export async function fetchReview(
  cookieHeader: string,
  reviewJobId: string,
): Promise<FetchReviewResult> {
  let response: Response;
  try {
    response = await fetch(
      `${CONTROL_PLANE_ORIGIN}/api/reviews/${encodeURIComponent(reviewJobId)}`,
      {
        headers: { cookie: cookieHeader },
        cache: "no-store",
      },
    );
  } catch {
    return { kind: "error" };
  }
  if (response.status === 401) {
    return { kind: "unauthenticated" };
  }
  if (response.status === 404) {
    return { kind: "not_found" };
  }
  if (!response.ok) {
    return { kind: "error" };
  }
  const review = (await response.json()) as ReviewSummary;
  return { kind: "ok", review };
}
