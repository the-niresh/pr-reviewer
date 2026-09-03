import { GithubMark } from "@/components/github-mark";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// The same relative path SignInPrompt uses everywhere else (DashboardState.tsx): a plain
// top-level navigation to the hosted control plane, not a fetch, so this works regardless
// of where /api/auth/github/sign-in is actually served. Only /dashboard and
// /dashboard/reviews are allowlisted server-side (github_oauth.py); /dashboard is the one
// that makes sense for a visitor who has never signed in before.
const SIGN_IN_URL = "/api/auth/github/sign-in?return_to=/dashboard";

const PILLARS = [
  {
    title: "Local first",
    body: "The review runs on your machine. Source and diffs never leave it, ever.",
  },
  {
    title: "Built for humans and agents",
    body: "A TUI, a web dashboard, and MCP, CLI, ACP, and A2A for other agents. One core, same review.",
  },
  {
    title: "Free, no plan to sign up for",
    body: "Nothing to buy and nothing to unlock later. Install it and it is all there.",
  },
] as const;

export default function HomePage() {
  return (
    <main className="mx-auto w-full max-w-5xl px-6">
      <section className="border-b py-[var(--space-section)]">
        <span className="text-primary font-mono text-xs tracking-[0.2em] uppercase">
          pr-reviewer
        </span>
        <h1 className="mt-5 max-w-[16ch] text-5xl leading-[1.05] font-semibold tracking-tight text-balance sm:text-6xl lg:text-7xl">
          The PR reviewer that{" "}
          <em className="text-primary not-italic">never leaves</em> your laptop
        </h1>
        <p className="text-muted-foreground mt-6 max-w-prose text-lg leading-relaxed">
          Findings, reasoning, and cost show up on the web. Your source, your diffs, and
          your model keys stay exactly where they are.
        </p>
        {/* The whole front door: without this, sign-in only exists on pages you already
            have to be signed in to reach. Same relative-path convention as SignInPrompt,
            same icon and wording as every other "sign in with GitHub" action in the app. */}
        <a
          href={SIGN_IN_URL}
          className={cn(buttonVariants({ size: "lg" }), "mt-9 gap-2")}
        >
          <GithubMark className="size-4" />
          Sign in with GitHub
        </a>
      </section>

      <section className="grid gap-px border-x-0 py-[var(--space-section)] sm:grid-cols-3 sm:gap-8">
        {PILLARS.map((pillar) => (
          <article key={pillar.title} className="sm:border-l sm:pl-6 sm:first:border-l-0 sm:first:pl-0">
            <h2 className="text-base font-semibold">{pillar.title}</h2>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              {pillar.body}
            </p>
          </article>
        ))}
      </section>

      <footer className="text-muted-foreground border-t py-8 font-mono text-xs">
        reviewer.niresh.tech
      </footer>
    </main>
  );
}
