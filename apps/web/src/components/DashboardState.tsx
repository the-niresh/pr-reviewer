import { CircleAlert } from "lucide-react";

/** Shared across every /dashboard/* page: the same "sign in" prompt and the same "could
 *  not load" notice everywhere, so a viewer never has to relearn what a given screen
 *  looks like when something other than real data is showing. */
export function SignInPrompt({ returnTo }: { returnTo: string }) {
  return (
    <div className="bg-card mt-8 rounded-lg border p-6">
      <h2 className="text-lg font-semibold tracking-tight">Sign in required</h2>
      <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
        Sign in with GitHub to see your reviews.
      </p>
      <a
        href={`/api/auth/github/sign-in?return_to=${encodeURIComponent(returnTo)}`}
        className="bg-primary text-primary-foreground hover:bg-primary/90 mt-5 inline-flex h-10 items-center rounded-md px-6 text-sm font-medium focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        Sign in with GitHub
      </a>
    </div>
  );
}

/** A load failure is never allowed to render as "there is nothing here": it says plainly
 *  that the data could not be fetched, distinct in both wording and colour from an
 *  honest empty state. */
export function LoadError() {
  return (
    <div className="border-destructive/40 bg-destructive/10 text-destructive mt-8 flex items-start gap-2 rounded-lg border p-6 text-sm">
      <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0" />
      <p className="leading-relaxed">
        Could not load your reviews from the control plane. This is not the same as having
        no reviews yet, try reloading in a moment.
      </p>
    </div>
  );
}
