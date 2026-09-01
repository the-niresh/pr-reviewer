import { readFileSync } from "node:fs";
import path from "node:path";

import styles from "./page.module.css";

type Scorecard = {
  precision_per_finding: number | string;
  precision_per_case: number | string;
  recall_per_finding: number | string;
  recall_per_case: number | string;
  false_findings_per_pr: number | string;
  cost_usd: number | string;
  reviewed_pr_count: number | string;
};

type FeatureFlag = {
  name: string;
  enabled: boolean;
  measurement: string;
};

const METRIC_LABELS: Record<keyof Scorecard, string> = {
  precision_per_finding: "Precision, per finding",
  precision_per_case: "Precision, per case",
  recall_per_finding: "Recall, per finding",
  recall_per_case: "Recall, per case",
  false_findings_per_pr: "False findings per PR",
  cost_usd: "Cost (USD)",
  reviewed_pr_count: "PRs reviewed",
};

const FLAG_LABELS: Record<string, string> = {
  retrieval: "Retrieval",
  code_graph: "Code graph",
  specialists: "Specialists",
  langgraph: "LangGraph",
};

function readJson<T>(relativePath: string): T {
  const filePath = path.join(process.cwd(), "..", "..", relativePath);
  return JSON.parse(readFileSync(filePath, "utf-8")) as T;
}

export default function ScorecardPage() {
  const scorecard = readJson<Scorecard>("docs/reports/scorecard.json");
  const flags = readJson<FeatureFlag[]>("docs/reports/feature_flags.json");
  const metricKeys = Object.keys(METRIC_LABELS) as (keyof Scorecard)[];

  return (
    <main className={styles.wrap}>
      <h1 className={styles.title}>Scorecard</h1>
      <p className={styles.intro}>
        Measured quality, or the real refusal. Nothing below is a placeholder.
      </p>

      <h2 className={styles.sectionTitle}>Quality</h2>
      <dl className={styles.metrics}>
        {metricKeys.map((key) => {
          const value = scorecard[key];
          const isRefusal = typeof value === "string";
          return (
            <div className={styles.metricRow} key={key}>
              <dt>{METRIC_LABELS[key]}</dt>
              <dd className={isRefusal ? styles.refusal : styles.value}>{value}</dd>
            </div>
          );
        })}
      </dl>

      <h2 className={styles.sectionTitle}>Feature flags</h2>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Feature</th>
            <th>Status</th>
            <th>Measurement</th>
          </tr>
        </thead>
        <tbody>
          {flags.map((flag) => (
            <tr key={flag.name}>
              <td>{FLAG_LABELS[flag.name] ?? flag.name}</td>
              <td>
                <span className={flag.enabled ? styles.on : styles.off}>
                  {flag.enabled ? "On" : "Off"}
                </span>
              </td>
              <td className={styles.refusal}>{flag.measurement}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
