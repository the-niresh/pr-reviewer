import { Badge } from "@/components/ui/badge";
import { SEVERITY_LEVELS, type SeverityLevel } from "@/lib/reviews";

const SEVERITY_LABEL: Record<SeverityLevel, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
};

// Same three semantic tones as everywhere else severity shows up, but the bar gets a
// fourth and fifth shade so critical and high (both "danger") and low and info (both
// "muted") stay visually distinguishable from each other, not just from medium.
const SEVERITY_BAR_COLOR: Record<SeverityLevel, string> = {
  critical: "bg-destructive",
  high: "bg-destructive/60",
  medium: "bg-[var(--warning)]",
  low: "bg-muted-foreground/45",
  info: "bg-muted-foreground/20",
};

const SEVERITY_BADGE_VARIANT: Record<SeverityLevel, "danger" | "warning" | "muted"> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "muted",
  info: "muted",
};

/** Severity readable two ways at once: a proportional bar for shape, and a count for the
 *  exact number, so "mostly critical" and "mostly info" never look like the same shape at
 *  a glance. */
export function SeverityBreakdown({ counts }: { counts: Record<SeverityLevel, number> }) {
  const total = SEVERITY_LEVELS.reduce((sum, level) => sum + counts[level], 0);

  return (
    <div>
      <div
        role="img"
        aria-label={`Findings by severity: ${SEVERITY_LEVELS.map(
          (level) => `${counts[level]} ${SEVERITY_LABEL[level]}`,
        ).join(", ")}`}
        className="bg-muted flex h-2.5 w-full overflow-hidden rounded-full"
      >
        {total > 0
          ? SEVERITY_LEVELS.filter((level) => counts[level] > 0).map((level) => (
              <div
                key={level}
                className={SEVERITY_BAR_COLOR[level]}
                style={{ width: `${(counts[level] / total) * 100}%` }}
              />
            ))
          : null}
      </div>
      <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
        {SEVERITY_LEVELS.map((level) => (
          <div key={level} className="flex items-center gap-1.5">
            <Badge variant={SEVERITY_BADGE_VARIANT[level]}>{SEVERITY_LABEL[level]}</Badge>
            <dd className="font-mono text-sm tabular-nums">{counts[level]}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
