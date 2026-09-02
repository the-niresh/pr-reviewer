import { cookies } from "next/headers";

import { Badge } from "@/components/ui/badge";

const CONTROL_PLANE_ORIGIN =
  process.env.NEXT_PUBLIC_CONTROL_PLANE_ORIGIN ?? "http://127.0.0.1:8000";

// GitHub cannot show a repository to an App that is not installed on it, so an
// installation is unavoidable. What is avoidable is making people find that out
// themselves: once signed in with no repositories, the page asks for it directly.
const APP_SLUG = process.env.NEXT_PUBLIC_GITHUB_APP_SLUG ?? "";
const INSTALL_URL = APP_SLUG
  ? `https://github.com/apps/${APP_SLUG}/installations/new`
  : "";

type ReceiptContextSource = {
  kind: string;
  name: string;
  reference: string;
};

type FindingReceipt = {
  provider: string | null;
  model: string | null;
  cost_usd: string | null;
  verification_status: "verified" | "asserted";
  verification_reason: string | null;
  sandbox_run_id: string | null;
  verification_detail: string | null;
  context_sources: ReceiptContextSource[];
};

type ReviewFinding = {
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

type ReviewSummary = {
  review_job_id: string;
  pull_request_number: number | null;
  head_sha: string | null;
  status: string;
  findings: ReviewFinding[];
};

type RepositoryReviews = {
  installation_id: number;
  github_repository_id: number;
  repository_name: string;
  reviews: ReviewSummary[];
};

type ReviewsResponse = {
  repositories: RepositoryReviews[];
};

/** Severity is semantic and deliberately separate from the brand accent, so
 *  "critical" can never read as "this is fine, it is just our colour". */
function severityTone(severity: string): "danger" | "warning" | "muted" {
  const s = severity.toLowerCase();
  if (s === "critical" || s === "high") return "danger";
  if (s === "medium") return "warning";
  return "muted";
}

export default async function ReviewsPage() {
  const cookieStore = await cookies();
  const response = await fetch(`${CONTROL_PLANE_ORIGIN}/api/reviews`, {
    headers: { cookie: cookieStore.toString() },
    cache: "no-store",
  });

  if (response.status === 401) {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Reviews</h1>
        <p className="text-muted-foreground mt-3">Sign in with GitHub to see your reviews.</p>
        <a
          href="/api/auth/github/sign-in?return_to=/dashboard/reviews"
          className="bg-primary text-primary-foreground hover:bg-primary/90 mt-6 inline-flex h-10 items-center rounded-md px-6 text-sm font-medium"
        >
          Sign in with GitHub
        </a>
      </main>
    );
  }

  const data = (await response.json()) as ReviewsResponse;

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Reviews</h1>
      {data.repositories.length === 0 ? (
        <div className="bg-card mt-8 rounded-lg border p-6">
          <h2 className="text-lg font-semibold tracking-tight">Connect GitHub</h2>
          <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
            No repositories yet. GitHub only lets this App see repositories you pick, so
            choose them once and reviews start arriving here.
          </p>
          {INSTALL_URL ? (
            <a
              href={INSTALL_URL}
              className="bg-primary text-primary-foreground hover:bg-primary/90 mt-5 inline-flex h-10 items-center rounded-md px-6 text-sm font-medium"
            >
              Choose repositories on GitHub
            </a>
          ) : (
            <p className="text-muted-foreground mt-5 text-sm italic">
              The install link is unavailable because the App slug is not configured on
              this deployment.
            </p>
          )}
        </div>
      ) : null}

      <div className="mt-10 flex flex-col gap-10">
        {data.repositories.map((repo) => (
          <section key={`${repo.installation_id}-${repo.github_repository_id}`}>
            <h2 className="font-mono text-sm font-semibold tracking-tight">
              {repo.repository_name}
            </h2>

            {repo.reviews.length === 0 ? (
              <p className="text-muted-foreground mt-2 text-sm">No reviews yet.</p>
            ) : (
              <div className="mt-4 flex flex-col gap-5">
                {repo.reviews.map((review) => (
                  <article
                    key={review.review_job_id}
                    className="bg-card overflow-hidden rounded-lg border"
                  >
                    <p className="bg-muted/40 flex items-center justify-between gap-3 border-b px-4 py-2.5 text-sm">
                      <span className="font-medium">
                        PR #{review.pull_request_number ?? "?"}
                      </span>
                      <Badge variant="muted">{review.status}</Badge>
                    </p>

                    {review.findings.map((finding) => (
                      <div key={finding.id} className="border-b px-4 py-4 last:border-b-0">
                        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                          <Badge variant={severityTone(finding.severity)}>
                            {finding.severity}
                          </Badge>
                          {finding.title}
                        </p>
                        <p className="text-muted-foreground mt-1.5 font-mono text-xs">
                          {finding.file_path}:{finding.line_start}
                        </p>
                        <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
                          {finding.rationale}
                        </p>

                        {finding.receipt ? (
                          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t pt-3">
                            {/* Verified and asserted must be tellable apart at a
                                glance, not by reading the label. */}
                            <Badge
                              variant={
                                finding.receipt.verification_status === "verified"
                                  ? "default"
                                  : "outline"
                              }
                              data-verification={finding.receipt.verification_status}
                            >
                              {finding.receipt.verification_status}
                            </Badge>
                            {finding.receipt.verification_status === "verified" ? (
                              <span className="text-muted-foreground text-xs">
                                {finding.receipt.verification_detail}
                                {finding.receipt.sandbox_run_id
                                  ? ` (run ${finding.receipt.sandbox_run_id})`
                                  : ""}
                              </span>
                            ) : (
                              <span className="text-muted-foreground text-xs italic">
                                {finding.receipt.verification_reason}
                              </span>
                            )}
                            {finding.receipt.model ? (
                              <span className="text-muted-foreground ml-auto font-mono text-xs tabular-nums">
                                {finding.receipt.provider}/{finding.receipt.model}
                                {finding.receipt.cost_usd
                                  ? ` · $${finding.receipt.cost_usd}`
                                  : ""}
                              </span>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </article>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
