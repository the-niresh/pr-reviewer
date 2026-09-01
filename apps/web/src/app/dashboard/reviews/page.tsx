import { cookies } from "next/headers";

import styles from "./page.module.css";

const CONTROL_PLANE_ORIGIN =
  process.env.NEXT_PUBLIC_CONTROL_PLANE_ORIGIN ?? "http://127.0.0.1:8000";

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

type AgentReasoning = {
  concern: string;
  reasoning: string;
};

type ReviewSummary = {
  review_job_id: string;
  pull_request_number: number | null;
  head_sha: string | null;
  status: string;
  findings: ReviewFinding[];
  reasoning: AgentReasoning[];
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

export default async function ReviewsPage() {
  const cookieStore = await cookies();
  const response = await fetch(`${CONTROL_PLANE_ORIGIN}/api/reviews`, {
    headers: { cookie: cookieStore.toString() },
    cache: "no-store",
  });

  if (response.status === 401) {
    return (
      <main className={styles.wrap}>
        <h1 className={styles.title}>Reviews</h1>
        <p className={styles.intro}>Sign in with GitHub to see your reviews.</p>
      </main>
    );
  }

  const data = (await response.json()) as ReviewsResponse;

  return (
    <main className={styles.wrap}>
      <h1 className={styles.title}>Reviews</h1>
      {data.repositories.length === 0 ? (
        <p className={styles.intro}>No repositories yet.</p>
      ) : null}
      {data.repositories.map((repo) => (
        <section
          key={`${repo.installation_id}-${repo.github_repository_id}`}
          className={styles.repo}
        >
          <h2 className={styles.repoName}>{repo.repository_name}</h2>
          {repo.reviews.length === 0 ? (
            <p className={styles.empty}>No reviews yet.</p>
          ) : (
            repo.reviews.map((review) => (
              <article key={review.review_job_id} className={styles.review}>
                <p className={styles.reviewMeta}>
                  <span>PR #{review.pull_request_number ?? "?"}</span>
                  <span className={styles.reviewStatus}>{review.status}</span>
                </p>
                {review.findings.map((finding) => (
                  <div key={finding.id} className={styles.finding}>
                    <p className={styles.findingTitle}>
                      <span className={styles.severity} data-severity={finding.severity}>
                        {finding.severity}
                      </span>
                      {finding.title}
                    </p>
                    <p className={styles.findingLocation}>
                      {finding.file_path}:{finding.line_start}
                    </p>
                    <p className={styles.findingRationale}>{finding.rationale}</p>
                    {finding.receipt ? (
                      <div className={styles.receipt}>
                        <span
                          className={styles.receiptBadge}
                          data-verification={finding.receipt.verification_status}
                        >
                          {finding.receipt.verification_status}
                        </span>
                        {finding.receipt.verification_status === "verified" ? (
                          <span className={styles.receiptDetail}>
                            {finding.receipt.verification_detail}
                            {finding.receipt.sandbox_run_id
                              ? ` (run ${finding.receipt.sandbox_run_id})`
                              : ""}
                          </span>
                        ) : (
                          <span className={styles.receiptDetail}>
                            {finding.receipt.verification_reason}
                          </span>
                        )}
                        {finding.receipt.model ? (
                          <span className={styles.receiptMeta}>
                            {finding.receipt.provider}/{finding.receipt.model}
                            {finding.receipt.cost_usd ? ` · $${finding.receipt.cost_usd}` : ""}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ))}
                {review.reasoning.map((entry, index) => (
                  <p className={styles.reasoning} key={`${entry.concern}-${index}`}>
                    <span className={styles.reasoningConcern}>{entry.concern}</span>
                    {entry.reasoning}
                  </p>
                ))}
              </article>
            ))
          )}
        </section>
      ))}
    </main>
  );
}
