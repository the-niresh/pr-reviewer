import { readFileSync } from "node:fs";
import path from "node:path";

import { Badge } from "@/components/ui/badge";

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
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Scorecard</h1>
      <p className="text-muted-foreground mt-3 max-w-prose leading-relaxed">
        Measured quality, or the real refusal. Nothing below is a placeholder.
      </p>

      <h2 className="mt-12 mb-4 text-xs font-medium tracking-[0.14em] uppercase">
        Quality
      </h2>
      <dl className="overflow-hidden rounded-lg border">
        {metricKeys.map((key) => {
          const value = scorecard[key];
          // A refusal is not a dimmed number, it is a different kind of answer,
          // so it is set in prose while a real measurement is set in tabular mono.
          const isRefusal = typeof value === "string";
          return (
            <div
              key={key}
              className="bg-card flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b px-4 py-3 last:border-b-0"
            >
              <dt className="text-sm">{METRIC_LABELS[key]}</dt>
              <dd
                className={
                  isRefusal
                    ? "text-muted-foreground max-w-prose text-sm italic"
                    : "font-mono text-sm tabular-nums"
                }
              >
                {value}
              </dd>
            </div>
          );
        })}
      </dl>

      <h2 className="mt-12 mb-4 text-xs font-medium tracking-[0.14em] uppercase">
        Feature flags
      </h2>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-muted/40 text-muted-foreground text-left">
              <th className="px-4 py-2.5 font-medium">Feature</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Measurement</th>
            </tr>
          </thead>
          <tbody>
            {flags.map((flag) => (
              <tr key={flag.name} className="bg-card border-t">
                <td className="px-4 py-3">{FLAG_LABELS[flag.name] ?? flag.name}</td>
                <td className="px-4 py-3">
                  <Badge variant={flag.enabled ? "default" : "muted"}>
                    {flag.enabled ? "On" : "Off"}
                  </Badge>
                </td>
                <td className="text-muted-foreground px-4 py-3 italic">
                  {flag.measurement}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
