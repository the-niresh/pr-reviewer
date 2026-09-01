"""Phase 27 Task 27.3: project a completed review's findings and per-agent reasoning to Neon.

Only columns control_plane/boundary.py's ALLOWLIST names ever get written here. Finding.evidence
has no column on review_findings and is never read by this module; a diff hunk or source snippet
has nowhere to go.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from pr_reviewer.contracts.finding import Concern, Finding
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
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


class ReviewFindingSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    concern: Concern
    severity: str
    category: str
    file_path: str
    line_start: int
    line_end: int
    title: str
    rationale: str
    verified: bool
    status: str


class AgentReasoningSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concern: Concern
    reasoning: str


class ReviewSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_job_id: str
    pull_request_number: int | None
    head_sha: str | None
    status: str
    findings: list[ReviewFindingSummary]
    reasoning: list[AgentReasoningSummary]


def reviews_for_repository(
    assertion: LiveInstallationAssertion,
    installation_id: int,
    github_repository_id: int,
) -> list[ReviewSummary] | None:
    """The web dashboard's read path. None means the viewer may not see this repository: the
    same outcome whether the installation does not exist, was never controlled by this viewer,
    or grants a different repository. Telling those apart is itself a cross-tenant leak, the
    same reason AccessDenialReason in github_auth.py collapses them (a scope miss is a 404).
    """
    granted = assertion.installations.get(installation_id)
    if granted is None or github_repository_id not in granted:
        return None

    with connection() as conn:
        job_rows = conn.execute(
            """
            select id, pull_request_number, head_sha, status
            from review_jobs
            where installation_id = %s and github_repository_id = %s
            order by created_at desc
            """,
            (installation_id, github_repository_id),
        ).fetchall()

        summaries: list[ReviewSummary] = []
        for job_row in job_rows:
            review_job_id = str(job_row["id"])
            finding_rows = conn.execute(
                """
                select id, concern, severity, category, file_path, line_start, line_end,
                       title, rationale, verified, status
                from review_findings
                where review_job_id = %s
                order by created_at
                """,
                (review_job_id,),
            ).fetchall()
            reasoning_rows = conn.execute(
                """
                select concern, reasoning from agent_reasoning
                where review_job_id = %s
                order by created_at
                """,
                (review_job_id,),
            ).fetchall()
            summaries.append(
                ReviewSummary(
                    review_job_id=review_job_id,
                    pull_request_number=job_row["pull_request_number"],
                    head_sha=job_row["head_sha"],
                    status=str(job_row["status"]),
                    findings=[ReviewFindingSummary(**dict(row)) for row in finding_rows],
                    reasoning=[AgentReasoningSummary(**dict(row)) for row in reasoning_rows],
                )
            )
    return summaries
