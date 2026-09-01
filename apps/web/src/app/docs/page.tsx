import Link from "next/link";

import styles from "./page.module.css";

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
    <main className={styles.wrap}>
      <h1 className={styles.title}>Docs</h1>
      <p className={styles.intro}>
        Everything the runner does, in the order you will hit it.
      </p>
      {SECTIONS.map((section) => (
        <section key={section.tag} className={styles.section}>
          <p className={styles.sectionTag}>{section.tag}</p>
          <h2 className={styles.sectionTitle}>{section.title}</h2>
          <p className={styles.sectionBody}>{section.body}</p>
          {section.tag === "Agent plugin" ? (
            <Link href="/docs/agents">See the four surfaces</Link>
          ) : null}
        </section>
      ))}
    </main>
  );
}
