import Link from "next/link";

const SECTIONS = [
  {
    tag: "Install",
    title: "Install the runner",
    body: "A single script installs the runner on your machine. It verifies its own checksum before it does anything else and fails closed if the checksum does not match. The command ships with the first published release.",
  },
  {
    tag: "GitHub connect",
    title: "Connect GitHub",
    body: "Open the TUI. With no GitHub connection it shows a sign-in link and refuses to review anything until you approve the App and pick the repositories it may see. There is no degraded mode without GitHub: no connection, no review.",
  },
  {
    tag: "BYOK",
    title: "Bring your own key",
    body: "Add a key from a well-known provider, at most five models each. Keys live in the OS keychain, with a file fallback when no keychain is available. A model key can never reach a hosted table, an event, or a trace export.",
  },
  {
    tag: "Agent plugin",
    title: "The agent plugin",
    body: "The same review is available to another coding agent through MCP, a JSON CLI, ACP, and A2A. One core, four adapters, and a parity test that keeps them from drifting apart.",
  },
] as const;

export default function DocsPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Docs</h1>
      <p className="text-muted-foreground mt-3 max-w-prose leading-relaxed">
        Everything the runner does, in the order you will hit it.
      </p>
      <div className="mt-12 flex flex-col">
        {SECTIONS.map((section) => (
          <section
            key={section.tag}
            className="border-t py-8 first:border-t-0 first:pt-0"
          >
            <p className="text-primary font-mono text-xs tracking-[0.14em] uppercase">
              {section.tag}
            </p>
            <h2 className="mt-2 text-xl font-semibold tracking-tight">{section.title}</h2>
            <p className="text-muted-foreground mt-3 max-w-prose leading-relaxed">
              {section.body}
            </p>
            {section.tag === "Agent plugin" ? (
              <Link
                href="/docs/agents"
                className="text-primary mt-4 inline-block rounded-sm text-sm underline-offset-4 hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                See the four surfaces
              </Link>
            ) : null}
          </section>
        ))}
      </div>
    </main>
  );
}
