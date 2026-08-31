"""Stale-safe, idempotent GitHub review posting. Runs on the runner.

Findings are passed in by the caller. This module never imports the hosted
database or the App-token connector. submit, list_reviews,
render_hunks, lookup, record_post, and record_event are injected, the same
way retrieval takes record_selection.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

import httpx

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.github import PullRequestRef
from pr_reviewer.contracts.review_context import FilePatch
from pr_reviewer.github.lifecycle import reviewed_head_is_current

Confidentiality = Literal["restricted", "ordinary"]
CommentSide = Literal["RIGHT", "LEFT"]
_NEW_LINE = re.compile(r"^(\d+)\| ")
_MARKER_PREFIX = "<!-- pr-reviewer:post:"


class StalePullRequestHead(RuntimeError):
    """The PR head moved after the review was computed and before the API call."""


@dataclass(frozen=True)
class RouteDecision:
    """The posting half of Task 15's GateDecision. Copied in, never recomputed."""

    allow_public_post: bool
    confidentiality: Confidentiality


@dataclass(frozen=True)
class ReviewComment:
    path: str
    line: int
    side: CommentSide
    body: str


@dataclass(frozen=True)
class ReviewSubmission:
    commit_id: str
    body: str
    comments: tuple[ReviewComment, ...]


@dataclass(frozen=True)
class PostedReview:
    github_review_id: str | None
    comment_ids: tuple[str, ...]
    response_status: int | None
    body: str
    comments: tuple[ReviewComment, ...]
    summary_only: bool = False
    idempotency_key: str = ""


def posting_idempotency_key(ref: PullRequestRef, head_sha: str, policy_version: str) -> str:
    return f"{ref.owner}/{ref.repository}#{ref.number}@{head_sha}:{policy_version}"


def post_review(
    ref: PullRequestRef,
    head_sha: str,
    findings: Sequence[tuple[Finding, RouteDecision]],
    idempotency_key: str,
    *,
    patches: Sequence[FilePatch],
    current_head_sha: Callable[[], str],
    submit: Callable[[ReviewSubmission], PostedReview],
    render_hunks: Callable[[FilePatch], str],
    list_reviews: Callable[[PullRequestRef], Sequence[PostedReview]] | None = None,
    lookup: Callable[[str], PostedReview | None] | None = None,
    record_post: Callable[[PostedReview], None] | None = None,
    record_event: Callable[[str, str, dict[str, str | int]], None] | None = None,
    policy_version: str = "v1",
) -> PostedReview | None:
    del policy_version
    existing = _existing(idempotency_key, ref, lookup, list_reviews)
    if existing is not None:
        return existing

    public = [
        (finding, decision)
        for finding, decision in findings
        if _is_public(finding, decision)
    ]
    if not public:
        return None

    comments = tuple(_anchor(finding, patches, render_hunks) for finding, _decision in public)
    inline = tuple(comment for comment in comments if comment is not None)
    titles = [finding.title for finding, _decision in public]
    body = f"{_marker(idempotency_key)}\n" + "\n".join(f"- {title}" for title in titles)
    submission = ReviewSubmission(commit_id=head_sha, body=body, comments=inline)

    live = current_head_sha()
    if not reviewed_head_is_current(head_sha, live):
        raise StalePullRequestHead(
            f"stale head: reviewed {head_sha} but live head is {live}"
        )

    try:
        posted = submit(submission)
    except httpx.TimeoutException:
        recovered = _existing(idempotency_key, ref, lookup, list_reviews)
        if recovered is None:
            raise
        posted = recovered

    posted = replace(
        posted,
        idempotency_key=idempotency_key,
        summary_only=len(inline) == 0,
        body=posted.body or body,
        comments=posted.comments or inline,
    )
    if record_post is not None:
        record_post(posted)
    _emit(record_event, findings, posted)
    return posted


def _is_public(finding: Finding, decision: RouteDecision) -> bool:
    if finding.status == "rejected":
        return False
    if decision.confidentiality == "restricted":
        return False
    return decision.allow_public_post


def _anchor(
    finding: Finding,
    patches: Sequence[FilePatch],
    render_hunks: Callable[[FilePatch], str],
) -> ReviewComment | None:
    patch = next((item for item in patches if item.path == finding.file_path), None)
    if patch is None:
        return None
    numbers = _new_side_numbers(render_hunks(patch))
    if finding.line_start not in numbers:
        return None
    return ReviewComment(
        path=patch.path,
        line=finding.line_start,
        side="RIGHT",
        body=finding.title,
    )


def _new_side_numbers(rendered: str) -> set[int]:
    numbers: set[int] = set()
    in_new = False
    for line in rendered.splitlines():
        if line.startswith("NEW "):
            in_new = True
            continue
        if line.startswith("OLD "):
            in_new = False
            continue
        if not in_new:
            continue
        match = _NEW_LINE.match(line)
        if match is not None:
            numbers.add(int(match.group(1)))
    return numbers


def _existing(
    key: str,
    ref: PullRequestRef,
    lookup: Callable[[str], PostedReview | None] | None,
    list_reviews: Callable[[PullRequestRef], Sequence[PostedReview]] | None,
) -> PostedReview | None:
    if lookup is not None:
        found = lookup(key)
        if found is not None:
            return found
    if list_reviews is None:
        return None
    needle = _marker(key)
    for review in list_reviews(ref):
        if needle in review.body:
            return replace(review, idempotency_key=key)
    return None


def _marker(key: str) -> str:
    return f"{_MARKER_PREFIX}{key} -->"


def _emit(
    record_event: Callable[[str, str, dict[str, str | int]], None] | None,
    findings: Sequence[tuple[Finding, RouteDecision]],
    posted: PostedReview,
) -> None:
    if record_event is None or posted.github_review_id is None or posted.response_status is None:
        return
    job_id = findings[0][0].review_job_id if findings else ""
    record_event(
        job_id,
        "github.review_posted",
        {
            "github_review_id": posted.github_review_id,
            "response_status": posted.response_status,
            "comment_count": len(posted.comment_ids),
        },
    )
