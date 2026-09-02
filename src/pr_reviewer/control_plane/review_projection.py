"""Phase 27 Task 27.3: project a completed review's findings and per-agent reasoning to Neon.

Only columns control_plane/boundary.py's ALLOWLIST names ever get written here. Finding.evidence
has no column on review_findings and is never read by this module; a diff hunk or source snippet
has nowhere to go.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pr_reviewer.contracts.finding import Concern, Finding, FindingStatus, Severity
from pr_reviewer.contracts.runner import AuthenticatedRunner, AuthorizationDenied, RunnerAuthDenied
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
from pr_reviewer.control_plane.github_oauth import LIVE_SIGN_IN_COOKIE_NAME, read_live_sign_in
from pr_reviewer.control_plane.repository_policy import authorize_repository
from pr_reviewer.control_plane.runner_auth import authenticate_runner
from pr_reviewer.db.client import Row, connection


@dataclass(frozen=True)
class ReceiptContextSourceInput:
    kind: Literal["diff", "retrieval", "profile", "graph"]
    name: str
    reference: str


@dataclass(frozen=True)
class ReceiptInput:
    """control_plane's own shape for what reviewer/receipt.py's FindingReceipt already proved.

    Deliberately not a direct import of FindingReceipt: control_plane/* must never import
    reviewer/* (Phase 1, enforced by test_package_boundaries.py). The caller -- runner-side code
    that already has a real FindingReceipt, where receipt.py:115 has already forced verified=true
    to cite a real sandbox run -- converts it to this shape before crossing the boundary. This
    module trusts that conversion; it does not re-derive verified from anything.
    """

    finding_id: str
    review_job_id: str
    prompt_version_id: str
    context_sources: Sequence[ReceiptContextSourceInput]
    verified: bool
    verification_reason: str | None = None
    sandbox_run_id: str | None = None
    command_id: str | None = None
    verification_detail: str | None = None


def project_review(
    review_job_id: str,
    findings: Sequence[Finding],
    receipts: Sequence[ReceiptInput] = (),
) -> None:
    for finding in findings:
        if finding.review_job_id != review_job_id:
            raise ValueError(
                f"finding {finding.id} belongs to review_job_id {finding.review_job_id}, "
                f"not {review_job_id}"
            )
    for validated_receipt in receipts:
        if validated_receipt.review_job_id != review_job_id:
            raise ValueError(
                f"receipt for finding {validated_receipt.finding_id} belongs to review_job_id "
                f"{validated_receipt.review_job_id}, not {review_job_id}"
            )
    receipts_by_finding_id = {receipt.finding_id: receipt for receipt in receipts}
    findings_by_id = {finding.id: finding for finding in findings}
    for finding_id, indexed_receipt in receipts_by_finding_id.items():
        matching_finding = findings_by_id.get(finding_id)
        if matching_finding is not None and indexed_receipt.verified != matching_finding.verified:
            raise ValueError(
                f"finding {finding_id} has verified={matching_finding.verified} but its "
                f"receipt says verified={indexed_receipt.verified}: never style an unverified "
                "finding as verified"
            )

    with connection() as conn, conn.transaction():
        for finding in findings:
            receipt = receipts_by_finding_id.get(finding.id)
            model_call_id = None
            verification_reason = None
            sandbox_run_id = None
            command_id = None
            verification_detail = None
            if receipt is not None:
                row = conn.execute(
                    """
                    select id from model_calls
                    where review_job_id = %s and prompt_version_id = %s
                    order by created_at desc limit 1
                    """,
                    (review_job_id, receipt.prompt_version_id),
                ).fetchone()
                model_call_id = row["id"] if row is not None else None
                verification_reason = receipt.verification_reason
                sandbox_run_id = receipt.sandbox_run_id
                command_id = receipt.command_id
                verification_detail = receipt.verification_detail

            conn.execute(
                """
                insert into review_findings (
                  id, review_job_id, concern, severity, category, file_path,
                  line_start, line_end, title, rationale, confidence,
                  verified, verification_method, public_safe, status,
                  model_call_id, verification_reason, sandbox_run_id, command_id,
                  verification_detail
                )
                values (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s
                )
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
                    model_call_id,
                    verification_reason,
                    sandbox_run_id,
                    command_id,
                    verification_detail,
                ),
            )

            if receipt is not None:
                for source in receipt.context_sources:
                    conn.execute(
                        """
                        insert into finding_context_sources (finding_id, kind, name, reference)
                        values (%s, %s, %s, %s)
                        """,
                        (finding.id, source.kind, source.name, source.reference),
                    )



class ReceiptContextSourceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    name: str
    reference: str


class FindingReceiptSummary(BaseModel):
    """The same receipt the TUI shows: receipt.py:115 already enforced, before this row was
    ever written, that a verified finding cites a real sandbox run. This model never re-derives
    verified from anything else; it only carries whichever half of ReceiptVerification the
    write path already chose.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str | None
    model: str | None
    prompt_version_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: str | None
    verification_status: Literal["verified", "asserted"]
    verification_reason: str | None
    sandbox_run_id: str | None
    command_id: str | None
    verification_detail: str | None
    context_sources: list[ReceiptContextSourceSummary]


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
    receipt: FindingReceiptSummary | None


# Task 33.E2: the web's plain-words explanation for a review that stopped because the runner's
# provider ran out of tokens. Deliberately not imported from tui/out_of_tokens.py: control_plane
# may never import models or tui (test_package_boundaries.py), and the pushed summary never
# carries a provider name or a reason string (tui/push_review_summary.py's ALLOWED_SUMMARY_FIELDS
# has neither -- reason is exactly the field the hosted boundary must never see). So this stays
# provider-agnostic on purpose, and it reuses the terminal's own vocabulary ("ran out of tokens",
# "switch provider") from tui/out_of_tokens.py so the two surfaces never describe the same
# situation in two different ways.
STOPPED_EARLY_MESSAGE = (
    "This review stopped early: the provider ran out of tokens partway through. The findings "
    "below are still complete and trustworthy for the code they cover. Add credits or switch "
    "provider on your machine to finish reviewing the rest."
)


class ReviewSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_job_id: str
    pull_request_number: int | None
    head_sha: str | None
    status: str
    stopped_early: bool
    stopped_early_message: str | None
    findings: list[ReviewFindingSummary]


def _finding_summary(conn: Connection[Row], row: Row) -> ReviewFindingSummary:
    source_rows = conn.execute(
        "select kind, name, reference from finding_context_sources where finding_id = %s "
        "order by created_at",
        (row["id"],),
    ).fetchall()
    context_sources = [ReceiptContextSourceSummary(**dict(source)) for source in source_rows]

    has_receipt = bool(row["verified"]) or context_sources or row["verification_reason"]
    receipt = None
    if has_receipt:
        receipt = FindingReceiptSummary(
            provider=row["provider"],
            model=row["model_name"],
            prompt_version_id=(
                str(row["prompt_version_id"]) if row["prompt_version_id"] is not None else None
            ),
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cost_usd=str(row["cost_usd"]) if row["cost_usd"] is not None else None,
            verification_status="verified" if row["verified"] else "asserted",
            verification_reason=row["verification_reason"],
            sandbox_run_id=row["sandbox_run_id"],
            command_id=row["command_id"],
            verification_detail=row["verification_detail"],
            context_sources=context_sources,
        )
    return ReviewFindingSummary(
        id=str(row["id"]),
        concern=row["concern"],
        severity=row["severity"],
        category=row["category"],
        file_path=row["file_path"],
        line_start=row["line_start"],
        line_end=row["line_end"],
        title=row["title"],
        rationale=row["rationale"],
        verified=row["verified"],
        status=row["status"],
        receipt=receipt,
    )


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
                select rf.id, rf.concern, rf.severity, rf.category, rf.file_path,
                       rf.line_start, rf.line_end, rf.title, rf.rationale, rf.verified,
                       rf.status, rf.verification_reason, rf.sandbox_run_id, rf.command_id,
                       rf.verification_detail, mc.provider, mc.model_name, mc.prompt_version_id,
                       mc.input_tokens, mc.output_tokens, mc.cost_usd
                from review_findings rf
                left join model_calls mc on mc.id = rf.model_call_id
                where rf.review_job_id = %s
                order by rf.created_at
                """,
                (review_job_id,),
            ).fetchall()
            findings = [_finding_summary(conn, row) for row in finding_rows]
            status = str(job_row["status"])
            stopped_early = status == "stopped_early"
            summaries.append(
                ReviewSummary(
                    review_job_id=review_job_id,
                    pull_request_number=job_row["pull_request_number"],
                    head_sha=job_row["head_sha"],
                    status=status,
                    stopped_early=stopped_early,
                    stopped_early_message=STOPPED_EARLY_MESSAGE if stopped_early else None,
                    findings=findings,
                )
            )
    return summaries


class RepositoryReviews(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    installation_id: int
    github_repository_id: int
    repository_name: str
    reviews: list[ReviewSummary]


class ReviewsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repositories: list[RepositoryReviews]


router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("", response_model=ReviewsResponse)
def list_reviews(
    request: Request,
    installation_id: int | None = None,
    github_repository_id: int | None = None,
) -> ReviewsResponse:
    """The web dashboard's only entry point into review_findings/agent_reasoning.

    No cookie, or a cookie that fails HMAC or has expired, is 401: the viewer is not signed in.
    A signed-in viewer naming a specific installation and repository they do not control gets
    404, same as reviews_for_repository's own None -- a scope miss is indistinguishable from
    not-found, never a distinct "forbidden".
    """
    cookie = request.cookies.get(LIVE_SIGN_IN_COOKIE_NAME, "")
    assertion = read_live_sign_in(cookie)
    if assertion is None:
        raise HTTPException(status_code=401, detail="not signed in")

    if installation_id is not None and github_repository_id is not None:
        reviews = reviews_for_repository(assertion, installation_id, github_repository_id)
        if reviews is None:
            raise HTTPException(status_code=404)
        repository_name = assertion.installations[installation_id][github_repository_id]
        return ReviewsResponse(
            repositories=[
                RepositoryReviews(
                    installation_id=installation_id,
                    github_repository_id=github_repository_id,
                    repository_name=repository_name,
                    reviews=reviews,
                )
            ]
        )

    repositories: list[RepositoryReviews] = []
    for granted_installation_id, repos in assertion.installations.items():
        for granted_repository_id, repository_name in repos.items():
            reviews = reviews_for_repository(
                assertion, granted_installation_id, granted_repository_id
            )
            repositories.append(
                RepositoryReviews(
                    installation_id=granted_installation_id,
                    github_repository_id=granted_repository_id,
                    repository_name=repository_name,
                    reviews=reviews or [],
                )
            )
    return ReviewsResponse(repositories=repositories)


# Task 33.A4: the receiving end of tui/push_review_summary.py. That module's ALLOWED_FINDING_FIELDS
# and ALLOWED_SUMMARY_FIELDS are the sending side's own allowlist; the two Pydantic models below are
# this endpoint's independent copy of the same shape, field for field, deliberately not shared code
# -- control_plane must never import tui (the hosted plane cannot depend on code that only makes
# sense holding a model key on someone's laptop). extra="forbid" on both models is what makes a
# mistake on the sending side loud: a payload carrying "reasoning", "diff", "source", or anything
# else outside this shape fails with a 422 naming the field, not a silent drop.
class PushedFindingBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concern: Concern
    severity: Severity
    file_path: str = Field(min_length=1)
    line_start: int = Field(gt=0)
    line_end: int = Field(gt=0)
    title: str = Field(min_length=1)
    status: FindingStatus

    @model_validator(mode="after")
    def validate_line_range(self) -> PushedFindingBody:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class PushedReviewSummaryBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_job_id: uuid.UUID
    installation_id: int
    github_repository_id: int
    pull_request_number: int
    head_sha: str = Field(min_length=1)
    status: Literal["completed", "stopped_early"]
    stopped_early: bool = False
    findings: list[PushedFindingBody] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stopped_early_matches_status(self) -> PushedReviewSummaryBody:
        if self.stopped_early != (self.status == "stopped_early"):
            raise ValueError("stopped_early must match status == 'stopped_early'")
        return self


class PushedReviewSummaryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["saved"] = "saved"


def _authenticate_runner_bearer(authorization: str | None) -> AuthenticatedRunner:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer credential")
    credential = authorization.removeprefix("Bearer ")
    authenticated = authenticate_runner(credential)
    if isinstance(authenticated, RunnerAuthDenied):
        raise HTTPException(status_code=401, detail=authenticated.reason)
    return authenticated


def save_pushed_review_summary(body: PushedReviewSummaryBody) -> None:
    """Idempotent on review_job_id: a retried push updates the review_jobs row in place (it is
    ordinary mutable state, not append-only) rather than inserting a second one, since (id) is
    its primary key. Findings are append-only by design (review_findings_append_only, migration
    202609020136) the same as every other writer of that table, so a retried push instead gets a
    deterministic id per finding (review_job_id + position) and "on conflict do nothing": the
    second copy of the same retry is a no-op, never a duplicate row.

    category, rationale, confidence, verified, verification_method and public_safe have no
    equivalent on the thin pushed shape -- Niresh's allowed-to-cross list for this path is
    narrower than Phase 27/30's (title, concern, severity, file_path, line numbers, status only,
    never rationale). They get the literal, honest value for "nothing was asserted here":
    verified=false and verification_method='not_applicable', never a fabricated confidence.
    """
    with connection() as conn, conn.transaction():
        conn.execute(
            """
            insert into review_jobs (
              id, delivery_id, status, installation_id, github_repository_id,
              pull_request_number, head_sha
            )
            values (%s, null, %s, %s, %s, %s, %s)
            on conflict (id) do update set
              status = excluded.status,
              installation_id = excluded.installation_id,
              github_repository_id = excluded.github_repository_id,
              pull_request_number = excluded.pull_request_number,
              head_sha = excluded.head_sha,
              updated_at = now()
            """,
            (
                str(body.review_job_id),
                body.status,
                body.installation_id,
                body.github_repository_id,
                body.pull_request_number,
                body.head_sha,
            ),
        )
        for index, finding in enumerate(body.findings):
            finding_id = f"{body.review_job_id}:{index}"
            conn.execute(
                """
                insert into review_findings (
                  id, review_job_id, concern, severity, category, file_path,
                  line_start, line_end, title, rationale, confidence,
                  verified, verification_method, public_safe, status
                )
                values (
                  %s, %s, %s, %s, '', %s, %s, %s, %s, '', 0,
                  false, 'not_applicable', true, %s
                )
                on conflict (id) do nothing
                """,
                (
                    finding_id,
                    str(body.review_job_id),
                    finding.concern,
                    finding.severity,
                    finding.file_path,
                    finding.line_start,
                    finding.line_end,
                    finding.title,
                    finding.status,
                ),
            )


@router.post("/summary", response_model=PushedReviewSummaryResult)
def push_review_summary_route(
    body: PushedReviewSummaryBody,
    authorization: str | None = Header(default=None),
) -> PushedReviewSummaryResult:
    """A paired runner's terminal pushes exactly one finished review here. Authenticated the same
    way the runner job protocol is (control_plane/runner_jobs.py's bearer credential), then
    re-authorized against the specific repository named in the body the same way
    token_broker.issue_job_token re-checks it: holding a valid credential is not the same as
    being assigned to this repository.
    """
    runner = _authenticate_runner_bearer(authorization)
    denial = authorize_repository(body.installation_id, body.github_repository_id, runner.runner_id)
    if isinstance(denial, AuthorizationDenied):
        raise HTTPException(status_code=403, detail=denial.reason)

    save_pushed_review_summary(body)
    return PushedReviewSummaryResult()
