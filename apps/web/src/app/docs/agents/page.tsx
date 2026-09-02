const SURFACES = [
  {
    tag: "MCP",
    title: "Model Context Protocol",
    body: "A JSON-RPC tool server. tools/list returns three tools; tools/call runs one of them.",
    commands: [
      "review_pull_request { owner, repository, pull_request }",
      "list_findings { review_id }",
      "list_remediation_prompts { review_id }",
    ],
  },
  {
    tag: "JSON CLI",
    title: "Machine-readable command line",
    body: "The same three operations as reviewer agent-json subcommands, one JSON object per line on stdout, never prose.",
    commands: [
      "reviewer agent-json review --owner OWNER --repository REPO --pull-request N",
      "reviewer agent-json findings --review-id ID",
      "reviewer agent-json remediation-prompts --review-id ID",
    ],
  },
  {
    tag: "ACP",
    title: "Agent Client Protocol",
    body: "The same three actions, named identically, for an ACP-speaking client to call directly.",
    commands: [
      "review_pull_request { owner, repository, pull_request }",
      "list_findings { review_id }",
      "list_remediation_prompts { review_id }",
    ],
  },
  {
    tag: "A2A",
    title: "Agent2Agent",
    body: "An agent card advertises one skill, pr-review, over JSON-RPC so another agent can request a review agent to agent.",
    commands: [
      "agent card: protocolVersion 0.3.0, preferredTransport JSONRPC",
      "skill: pr-review (start a review, or fetch findings and remediation prompts)",
    ],
  },
] as const;

export default function AgentSurfacesPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Agent surfaces</h1>
      <p className="text-muted-foreground mt-3 max-w-prose leading-relaxed">
        One core, four adapters. A parity test keeps them from drifting apart, so the same
        review and the same findings come back no matter which surface asked.
      </p>
      <div className="mt-12 flex flex-col gap-5">
        {SURFACES.map((surface) => (
          <section key={surface.tag} className="bg-card rounded-lg border p-5">
            <p className="text-primary font-mono text-xs tracking-[0.14em] uppercase">
              {surface.tag}
            </p>
            <h2 className="mt-2 text-lg font-semibold tracking-tight">{surface.title}</h2>
            <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
              {surface.body}
            </p>
            <ul className="mt-4 flex flex-col gap-1.5 overflow-x-auto">
              {surface.commands.map((command) => (
                <li
                  key={command}
                  className="bg-muted/50 rounded-md px-3 py-2 font-mono text-xs whitespace-pre"
                >
                  {command}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <p className="text-muted-foreground border-primary/50 mt-10 max-w-prose border-l-2 pl-4 text-sm leading-relaxed">
        Every surface refuses the same way when GitHub is not connected: a typed refusal
        naming the reason, never a guess and never a degraded review.
      </p>
    </main>
  );
}
