import { cookies } from "next/headers";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { LoadError, SignInPrompt } from "@/components/DashboardState";
import { fetchReviews, severityTone, worstSeverity } from "@/lib/reviews";

export const metadata = {
  title: "Reviews",
};

export default async function ReviewsPage() {
  const cookieStore = await cookies();
  const result = await fetchReviews(cookieStore.toString());

  if (result.kind === "unauthenticated") {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Reviews</h1>
        <SignInPrompt returnTo="/dashboard/reviews" />
      </main>
    );
  }

  if (result.kind === "error") {
    return (
      <main className="mx-auto w-full max-w-4xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Reviews</h1>
        <LoadError />
      </main>
    );
  }

  const reviews = result.data.repositories
    .flatMap((repo) =>
      repo.reviews.map((review) => ({ ...review, repository_name: repo.repository_name })),
    )
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Reviews</h1>

      {result.data.repositories.length === 0 ? (
        <div className="bg-card mt-8 rounded-lg border p-6">
          <h2 className="text-lg font-semibold tracking-tight">Connect GitHub</h2>
          <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
            No repositories yet. GitHub only lets this App see repositories you pick, so
            choose them once and reviews start arriving here.
          </p>
          <Link
            href="/dashboard/settings"
            className="text-primary mt-4 inline-block rounded-sm text-sm underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            Check connected repositories
          </Link>
        </div>
      ) : reviews.length === 0 ? (
        <div className="bg-card mt-8 rounded-lg border p-6">
          <h2 className="text-lg font-semibold tracking-tight">No reviews yet</h2>
          <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
            Reviews show up here once the runner on your machine finishes one against a
            connected repository.
          </p>
        </div>
      ) : (
        // Wide content scrolls inside its own container; the page body never scrolls
        // sideways even on a narrow viewport with six columns of data.
        <div className="mt-8 overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[46rem] border-collapse text-sm">
            <thead>
              <tr className="bg-muted/40 text-muted-foreground text-left">
                <th className="px-4 py-2.5 font-medium">Repository</th>
                <th className="px-4 py-2.5 font-medium">Pull request</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Findings</th>
                <th className="px-4 py-2.5 font-medium">Worst severity</th>
                <th className="px-4 py-2.5 font-medium">When</th>
              </tr>
            </thead>
            <tbody>
              {reviews.map((review) => {
                const worst = worstSeverity(review.findings);
                return (
                  // The stretched-link pattern: the anchor's ::after covers the whole
                  // row, so the entire row opens the review without any client JS, while
                  // the anchor itself still carries a real, keyboard-visible focus ring.
                  <tr
                    key={review.review_job_id}
                    className="bg-card hover:bg-secondary/50 relative border-t transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-xs">
                      <Link
                        href={`/dashboard/reviews/${review.review_job_id}`}
                        className="after:absolute after:inset-0 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
                      >
                        {review.repository_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">#{review.pull_request_number ?? "?"}</td>
                    <td className="px-4 py-3">
                      {/* stopped_early must never read as a finished review. */}
                      <Badge variant={review.stopped_early ? "warning" : "muted"}>
                        {review.stopped_early ? "Stopped early" : review.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 font-mono tabular-nums">
                      {review.findings.length}
                    </td>
                    <td className="px-4 py-3">
                      {worst ? (
                        <Badge variant={severityTone(worst)}>{worst}</Badge>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="text-muted-foreground px-4 py-3">
                      <time dateTime={review.created_at}>
                        {new Date(review.created_at).toLocaleDateString()}
                      </time>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
