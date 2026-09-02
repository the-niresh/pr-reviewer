import { cookies } from "next/headers";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadError, SignInPrompt } from "@/components/DashboardState";
import { SeverityBreakdown } from "@/components/SeverityBreakdown";
import {
  fetchReviews,
  SEVERITY_LEVELS,
  severityTone,
  worstSeverity,
  type SeverityLevel,
} from "@/lib/reviews";

export const metadata = {
  title: "Dashboard",
};

const RECENT_REVIEW_COUNT = 5;

export default async function DashboardPage() {
  const cookieStore = await cookies();
  const result = await fetchReviews(cookieStore.toString());

  if (result.kind === "unauthenticated") {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <SignInPrompt returnTo="/dashboard" />
      </main>
    );
  }

  if (result.kind === "error") {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <LoadError />
      </main>
    );
  }

  const reviews = result.data.repositories.flatMap((repo) =>
    repo.reviews.map((review) => ({ ...review, repository_name: repo.repository_name })),
  );

  if (reviews.length === 0) {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        {/* Honest empty state: no reviews yet is not an error, and it says what to do
            next instead of just sitting there blank. */}
        <div className="bg-card mt-8 rounded-lg border p-6">
          <h2 className="text-lg font-semibold tracking-tight">No reviews yet</h2>
          <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
            Reviews show up here once the runner on your machine finishes one. Open it
            against a pull request on a repository you have connected, and it lands here
            as soon as it is done.
          </p>
          <Link
            href="/dashboard/settings"
            className="text-primary mt-4 inline-block rounded-sm text-sm underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            Check connected repositories
          </Link>
        </div>
      </main>
    );
  }

  const totalFindings = reviews.reduce((sum, review) => sum + review.findings.length, 0);

  const severityCounts = Object.fromEntries(
    SEVERITY_LEVELS.map((level) => [level, 0]),
  ) as Record<SeverityLevel, number>;
  for (const review of reviews) {
    for (const finding of review.findings) {
      const level = finding.severity.toLowerCase();
      if ((SEVERITY_LEVELS as readonly string[]).includes(level)) {
        severityCounts[level as SeverityLevel] += 1;
      }
    }
  }

  const recentReviews = [...reviews]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, RECENT_REVIEW_COUNT);

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
      <p className="text-muted-foreground mt-3 max-w-prose leading-relaxed">
        A quick read on what your reviews have found so far.
      </p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-muted-foreground text-xs font-medium tracking-[0.14em] uppercase">
              Reviews
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-3xl tabular-nums">{reviews.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-muted-foreground text-xs font-medium tracking-[0.14em] uppercase">
              Findings
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-3xl tabular-nums">{totalFindings}</p>
          </CardContent>
        </Card>
      </div>

      <h2 className="mt-12 mb-4 text-xs font-medium tracking-[0.14em] uppercase">
        Findings by severity
      </h2>
      <Card>
        <CardContent>
          <SeverityBreakdown counts={severityCounts} />
        </CardContent>
      </Card>

      <h2 className="mt-12 mb-4 text-xs font-medium tracking-[0.14em] uppercase">
        Recent reviews
      </h2>
      <div className="overflow-hidden rounded-lg border">
        {recentReviews.map((review) => {
          const worst = worstSeverity(review.findings);
          return (
            <Link
              key={review.review_job_id}
              href={`/dashboard/reviews/${review.review_job_id}`}
              className="bg-card hover:bg-secondary/50 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b px-4 py-3 text-sm transition-colors last:border-b-0 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:-outline-offset-2 focus-visible:outline-none"
            >
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-muted-foreground truncate font-mono text-xs">
                  {review.repository_name}
                </span>
                <span className="font-medium">PR #{review.pull_request_number ?? "?"}</span>
              </span>
              <span className="flex items-center gap-3">
                {/* stopped_early must never read as a finished review, even summarised
                    down to a single badge here. */}
                {review.stopped_early ? (
                  <Badge variant="warning">Stopped early</Badge>
                ) : worst ? (
                  <Badge variant={severityTone(worst)}>{worst}</Badge>
                ) : (
                  <Badge variant="muted">No findings</Badge>
                )}
                <time dateTime={review.created_at} className="text-muted-foreground text-xs">
                  {new Date(review.created_at).toLocaleDateString()}
                </time>
              </span>
            </Link>
          );
        })}
      </div>
    </main>
  );
}
