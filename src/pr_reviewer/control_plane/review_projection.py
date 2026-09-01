"""Phase 27 Task 27.3: project a completed review's findings and per-agent reasoning to Neon.

Only columns control_plane/boundary.py's ALLOWLIST names ever get written here. Finding.evidence
has no column on review_findings and is never read by this module; a diff hunk or source snippet
has nowhere to go.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pr_reviewer.contracts.finding import Concern, Finding
from pr_reviewer.db.client import connection


@dataclass(frozen=True)
class AgentReasoningEntry:
    review_job_id: str
    concern: Concern
    reasoning: str


def project_review(
    review_job_id: str,
    findings: Sequence[Finding],
    reasoning_entries: Sequence[AgentReasoningEntry] = (),
) -> None:
    for finding in findings:
        if finding.review_job_id != review_job_id:
            raise ValueError(
                f"finding {finding.id} belongs to review_job_id {finding.review_job_id}, "
                f"not {review_job_id}"
            )
    for entry in reasoning_entries:
        if entry.review_job_id != review_job_id:
            raise ValueError(
                f"reasoning entry belongs to review_job_id {entry.review_job_id}, "
                f"not {review_job_id}"
            )

    with connection() as conn, conn.transaction():
        for finding in findings:
            conn.execute(
                """
                insert into review_findings (
                  id, review_job_id, concern, severity, category, file_path,
                  line_start, line_end, title, rationale, confidence,
                  verified, verification_method, public_safe, status
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    finding.id,
                    finding.review_job_id,
                    finding.concern,
                    finding.severity,
                    finding.category,
                    finding.file_path,
                    finding.line_start,
                    finding.line_end,
                    finding.title,
                    finding.rationale,
                    finding.confidence,
                    finding.verified,
                    finding.verification_method,
                    finding.public_safe,
                    finding.status,
                ),
            )

        for entry in reasoning_entries:
            conn.execute(
                """
                insert into agent_reasoning (review_job_id, concern, reasoning)
                values (%s, %s, %s)
                """,
                (entry.review_job_id, entry.concern, entry.reasoning),
            )
