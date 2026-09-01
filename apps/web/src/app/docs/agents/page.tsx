import styles from "./page.module.css";

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
    <main className={styles.wrap}>
      <h1 className={styles.title}>Agent surfaces</h1>
      <p className={styles.intro}>
        One core, four adapters. A parity test keeps them from drifting apart, so the same
        review and the same findings come back no matter which surface asked.
      </p>
      {SURFACES.map((surface) => (
        <section key={surface.tag} className={styles.section}>
          <p className={styles.sectionTag}>{surface.tag}</p>
          <h2 className={styles.sectionTitle}>{surface.title}</h2>
          <p className={styles.sectionBody}>{surface.body}</p>
          <ul className={styles.commands}>
            {surface.commands.map((command) => (
              <li key={command}>{command}</li>
            ))}
          </ul>
        </section>
      ))}
      <p className={styles.refusalNote}>
        Every surface refuses the same way when GitHub is not connected: a typed refusal naming
        the reason, never a guess and never a degraded review.
      </p>
    </main>
  );
}
