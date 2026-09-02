import { Badge } from "@/components/ui/badge";
import { severityTone, type ReviewFinding } from "@/lib/reviews";

/** One finding, full detail: severity, file path and line range, title, rationale, and the
 *  verification receipt where verified and asserted stay tellable apart at a glance rather
 *  than by reading the label (a filled badge for a real sandbox run, an outline for an
 *  unverified claim). Shared between the single-review page and anywhere else a finding
 *  needs to render in full. */
export function FindingCard({ finding }: { finding: ReviewFinding }) {
  return (
    <div className="border-b px-4 py-4 last:border-b-0">
      <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
        <Badge variant={severityTone(finding.severity)}>{finding.severity}</Badge>
        {finding.title}
      </p>
      <p className="text-muted-foreground mt-1.5 font-mono text-xs">
        {finding.file_path}:{finding.line_start}
        {finding.line_end !== finding.line_start ? `-${finding.line_end}` : ""}
      </p>
      <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-relaxed">
        {finding.rationale}
      </p>

      {finding.receipt ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t pt-3">
          {/* Verified and asserted must be tellable apart at a glance, not by reading
              the label. */}
          <Badge
            variant={finding.receipt.verification_status === "verified" ? "default" : "outline"}
            data-verification={finding.receipt.verification_status}
          >
            {finding.receipt.verification_status}
          </Badge>
          {finding.receipt.verification_status === "verified" ? (
            <span className="text-muted-foreground text-xs">
              {finding.receipt.verification_detail}
              {finding.receipt.sandbox_run_id ? ` (run ${finding.receipt.sandbox_run_id})` : ""}
            </span>
          ) : (
            <span className="text-muted-foreground text-xs italic">
              {finding.receipt.verification_reason}
            </span>
          )}
          {finding.receipt.model ? (
            <span className="text-muted-foreground ml-auto font-mono text-xs tabular-nums">
              {finding.receipt.provider}/{finding.receipt.model}
              {finding.receipt.cost_usd ? ` · $${finding.receipt.cost_usd}` : ""}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
