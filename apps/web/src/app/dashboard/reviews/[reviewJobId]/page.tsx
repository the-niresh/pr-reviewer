import { cookies } from "next/headers";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { FindingCard } from "@/components/FindingCard";
import { LoadError, SignInPrompt } from "@/components/DashboardState";
import { fetchReview } from "@/lib/reviews";

export const metadata = {
  title: "Review",
};

type PageProps = {
  params: Promise<{ reviewJobId: string }>;
};

export default async function ReviewDetailPage({ params }: PageProps) {
  const { reviewJobId } = await params;
  const cookieStore = await cookies();
  const result = await fetchReview(cookieStore.toString(), reviewJobId);

  if (result.kind === "unauthenticated") {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Review</h1>
        {/* A per-review path is not in the hosted allowlist (github_oauth.py's
            ALLOWED_RETURN_TO_PATHS is only /dashboard and /dashboard/reviews); passing one
            here made the sign-in link 400 at the control plane. */}
        <SignInPrompt returnTo="/dashboard/reviews" />
      </main>
    );
  }

  if (result.kind === "error") {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Review</h1>
        <LoadError />
      </main>
    );
  }

  if (result.kind === "not_found") {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-semibold tracking-tight">Review</h1>
        {/* Deliberately the same message whether this review never existed or belongs to
            a repository this account was never granted -- telling those apart would leak
            which review ids are real, the same reason the API collapses both to 404. */}
        <div className="bg-card mt-8 rounded-lg border p-6">
          <h2 className="text-lg font-semibold tracking-tight">Review not found</h2>
          <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
            This review does not exist, or is not one this account has permission to see.
          </p>
          <Link
            href="/dashboard/reviews"
            className="text-primary mt-4 inline-block rounded-sm text-sm underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            Back to reviews
          </Link>
        </div>
      </main>
    );
  }

  const { review } = result;

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <Link
        href="/dashboard/reviews"
        className="text-muted-foreground hover:text-foreground rounded-sm text-sm underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        Back to reviews
      </Link>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          PR #{review.pull_request_number ?? "?"}
        </h1>
        {/* A review that stopped early because tokens ran out must never present as
            complete: the badge names its real state, never the raw status enum. */}
        <Badge variant={review.stopped_early ? "warning" : "muted"}>
          {review.stopped_early ? "Stopped early" : review.status}
        </Badge>
      </div>
      <p className="text-muted-foreground mt-2 text-sm">
        <time dateTime={review.created_at}>{new Date(review.created_at).toLocaleString()}</time>
        {review.head_sha ? (
          <span className="ml-2 font-mono text-xs">{review.head_sha.slice(0, 12)}</span>
        ) : null}
      </p>

      {review.stopped_early ? (
        <p className="mt-6 rounded-lg border bg-[var(--warning)]/10 px-4 py-3 text-sm leading-relaxed text-[var(--warning)]">
          {review.stopped_early_message}
        </p>
      ) : null}

      <div className="mt-8 overflow-hidden rounded-lg border">
        {review.findings.length === 0 ? (
          <p className="text-muted-foreground px-4 py-4 text-sm">
            No findings were recorded for this review.
          </p>
        ) : (
          review.findings.map((finding) => (
            <FindingCard key={finding.id} finding={finding} />
          ))
        )}
      </div>
    </main>
  );
}
