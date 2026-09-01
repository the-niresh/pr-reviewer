import Link from "next/link";

import styles from "./page.module.css";

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
    <main>
      <section className={styles.hero}>
        <span className={styles.eyebrow}>pr-reviewer</span>
        <h1 className={styles.headline}>
          The PR reviewer that <em>never leaves</em> your laptop
        </h1>
        <p className={styles.subhead}>
          Findings, reasoning, and cost show up on the web. Your source, your diffs, and your
          model keys stay exactly where they are.
        </p>
        <Link href="/onboarding" className={styles.cta}>
          Connect GitHub
        </Link>
      </section>

      <section className={styles.pillars}>
        {PILLARS.map((pillar) => (
          <article key={pillar.title} className={styles.pillar}>
            <h2 className={styles.pillarTitle}>{pillar.title}</h2>
            <p className={styles.pillarBody}>{pillar.body}</p>
          </article>
        ))}
      </section>

      <footer className={styles.footer}>reviewer.niresh.tech</footer>
    </main>
  );
}
