"""Failing tests for stale-safe GitHub review posting (master Task 17).

Findings stay on the runner. post_review takes an injected submit callable, the same
way retrieval takes record_selection, so finding text never crosses onto Neon.
Routing is consumed as RouteDecision; this file does not call route_finding.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import httpx
import pytest

from pr_reviewer.contracts.finding import Finding
from pr_reviewer.contracts.github import PullRequestRef
from pr_reviewer.contracts.review_context import FilePatch

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
HEAD_SHA = "a" * 40
OTHER_SHA = "b" * 40
POLICY = "policy-v1"
PATCH = (
    "@@ -1,2 +1,3 @@\n"
    " def foo():\n"
    "     return 1\n"
    "+    return 2\n"
)
DELETED_PATCH = "@@ -1,2 +1,1 @@\n def foo():\n-    return 1\n"
RENAME_PATCH = "@@ -1,1 +1,1 @@\n-old\n+new\n"


def _ref() -> PullRequestRef:
    return PullRequestRef(owner="acme", repository="widgets", number=17)


def _decision(
    *,
    allow_public_post: bool = True,
    confidentiality: str = "ordinary",
) -> Any:
    from pr_reviewer.github.post_review import RouteDecision

    return RouteDecision(
        allow_public_post=allow_public_post,
        confidentiality=confidentiality,  # type: ignore[arg-type]
    )


def _finding(**overrides: object) -> Finding:
    payload: dict[str, object] = {
        "id": "finding-1",
        "review_job_id": "job-17",
        "concern": "correctness",
        "severity": "medium",
        "category": "null-check",
        "file_path": "app.py",
        "line_start": 3,
        "line_end": 3,
        "title": "Return value changed",
        "rationale": "foo now returns 2.",
        "evidence": ["app.py:3"],
        "confidence": 0.8,
        "verified": True,
        "verification_method": "static",
        "public_safe": True,
        "status": "draft",
    }
    payload.update(overrides)
    return Finding.model_validate(payload)


def _patch(**overrides: str) -> FilePatch:
    fields: dict[str, str | None] = {"path": "app.py", "patch": PATCH, "previous_path": None}
    fields.update(overrides)
    return FilePatch(
        path=str(fields["path"]),
        patch=str(fields["patch"]),
        previous_path=fields["previous_path"],
    )


def _key() -> str:
    from pr_reviewer.github.post_review import posting_idempotency_key

    return posting_idempotency_key(_ref(), HEAD_SHA, POLICY)


class FakeGitHub:
    def __init__(self) -> None:
        self.submissions: list[Any] = []
        self.timeout_once = False
        self.server_reviews: list[Any] = []

    def submit(self, submission: Any) -> Any:
        from pr_reviewer.github.post_review import PostedReview

        if self.timeout_once:
            self.timeout_once = False
            posted = PostedReview(
                github_review_id="rev-server",
                comment_ids=("c-1",),
                response_status=201,
                body=submission.body,
                comments=tuple(submission.comments),
            )
            self.server_reviews.append(posted)
            raise httpx.TimeoutException("timed out after GitHub accepted the review")
        self.submissions.append(submission)
        posted = PostedReview(
            github_review_id=f"rev-{len(self.submissions)}",
            comment_ids=tuple(f"c-{i}" for i in range(len(submission.comments))),
            response_status=201,
            body=submission.body,
            comments=tuple(submission.comments),
        )
        self.server_reviews.append(posted)
        return posted

    def list_reviews(self, ref: PullRequestRef) -> list[Any]:
        del ref
        return list(self.server_reviews)


def _post(
    github: FakeGitHub,
    findings: list[tuple[Finding, Any]],
    *,
    patches: list[FilePatch] | None = None,
    current_head: str = HEAD_SHA,
    sha_fn: Any = None,
    lookup: Any = None,
    record_post: Any = None,
    record_event: Any = None,
    events: list[str] | None = None,
) -> Any:
    from pr_reviewer.github.post_review import post_review
    from pr_reviewer.reviewer.hunk_format import render_hunks

    store: dict[str, Any] = {}

    def default_lookup(key: str) -> Any:
        return store.get(key)

    def default_record(posted: Any) -> None:
        store[posted.idempotency_key] = posted

    def current() -> str:
        if events is not None:
            events.append("sha")
        return current_head if sha_fn is None else sha_fn()

    def render(patch: FilePatch) -> str:
        if events is not None:
            events.append("render")
        return render_hunks(patch)

    def submit(submission: Any) -> Any:
        if events is not None:
            events.append("submit")
        return github.submit(submission)

    return post_review(
        _ref(),
        HEAD_SHA,
        findings,
        _key(),
        patches=patches or [_patch()],
        current_head_sha=current,
        submit=submit,
        list_reviews=github.list_reviews,
        render_hunks=render,
        lookup=lookup or default_lookup,
        record_post=record_post or default_record,
        record_event=record_event,
        policy_version=POLICY,
    )


def test_head_sha_is_checked_immediately_before_submit_not_at_the_start() -> None:
    events: list[str] = []
    github = FakeGitHub()
    _post(github, [(_finding(), _decision())], events=events)
    assert "render" in events
    assert events.index("render") < events.index("sha")
    assert events[events.index("submit") - 1] == "sha"


def test_stale_head_sha_does_not_post() -> None:
    from pr_reviewer.github.post_review import StalePullRequestHead

    github = FakeGitHub()
    with pytest.raises(StalePullRequestHead, match="stale|head"):
        _post(github, [(_finding(), _decision())], current_head=OTHER_SHA)
    assert github.submissions == []


def test_one_review_per_repository_pr_head_sha_and_policy_version() -> None:
    github = FakeGitHub()
    first = _post(github, [(_finding(), _decision())])
    second = _post(github, [(_finding(), _decision())])
    assert first.github_review_id == second.github_review_id
    assert len(github.submissions) == 1


def test_timeout_after_server_success_does_not_double_post() -> None:
    github = FakeGitHub()
    github.timeout_once = True
    first = _post(github, [(_finding(), _decision())])
    assert first.github_review_id == "rev-server"
    assert len(github.submissions) == 0
    second = _post(github, [(_finding(), _decision())])
    assert second.github_review_id == "rev-server"
    assert len(github.submissions) == 0


def test_renamed_file_comment_uses_the_new_path() -> None:
    github = FakeGitHub()
    finding = _finding(file_path="new.py", line_start=1, line_end=1, title="renamed title")
    _post(
        github,
        [(finding, _decision())],
        patches=[_patch(path="new.py", patch=RENAME_PATCH, previous_path="old.py")],
    )
    comments = github.submissions[0].comments
    assert comments[0].path == "new.py"
    assert "old.py" not in comments[0].path


def test_deleted_line_is_not_a_right_side_anchor() -> None:
    github = FakeGitHub()
    finding = _finding(line_start=2, line_end=2, title="deleted line finding")
    _post(github, [(finding, _decision())], patches=[_patch(patch=DELETED_PATCH)])
    comments = github.submissions[0].comments
    assert all(comment.side != "RIGHT" or comment.line != 2 for comment in comments)


def test_outdated_line_falls_back_to_summary_only() -> None:
    github = FakeGitHub()
    finding = _finding(line_start=99, line_end=99, title="outdated line finding")
    result = _post(github, [(finding, _decision())])
    assert result.summary_only is True
    assert github.submissions[0].comments == ()
    assert "outdated line finding" in github.submissions[0].body


def test_no_valid_line_anchor_posts_summary_only() -> None:
    github = FakeGitHub()
    finding = _finding(file_path="missing.py", title="unanchored finding")
    result = _post(github, [(finding, _decision())])
    assert result.summary_only is True
    assert github.submissions[0].comments == ()


def test_restricted_security_finding_produces_no_public_comment() -> None:
    github = FakeGitHub()
    finding = _finding(
        concern="security",
        severity="critical",
        public_safe=False,
        title="SQL injection in auth.ts line 42",
        rationale="User input reaches SQL text.",
    )
    result = _post(
        github,
        [(finding, _decision(allow_public_post=False, confidentiality="restricted"))],
    )
    assert result is None or result.github_review_id is None
    assert github.submissions == []


def test_restricted_finding_is_absent_not_redacted_when_mixed_with_public() -> None:
    github = FakeGitHub()
    secret = _finding(
        id="finding-secret",
        concern="security",
        title="SQL injection in auth.ts line 42",
        rationale="exploit steps belong here",
        public_safe=False,
    )
    public = _finding(id="finding-public", title="Return value changed")
    _post(
        github,
        [
            (secret, _decision(allow_public_post=False, confidentiality="restricted")),
            (public, _decision()),
        ],
    )
    payload = github.submissions[0]
    blob = payload.body + "".join(comment.body for comment in payload.comments)
    assert "SQL injection" not in blob
    assert "exploit steps" not in blob
    assert "redacted" not in blob.lower()
    assert "Return value changed" in blob


def test_rejected_and_unverified_findings_never_enter_the_public_body() -> None:
    github = FakeGitHub()
    rejected = _finding(id="finding-rejected", title="rejected finding", status="rejected")
    unverified = _finding(id="finding-unverified", title="unverified finding", verified=False)
    public = _finding(id="finding-public", title="Return value changed")
    _post(
        github,
        [
            (rejected, _decision()),
            (unverified, _decision(allow_public_post=False)),
            (public, _decision()),
        ],
    )
    blob = github.submissions[0].body + "".join(
        comment.body for comment in github.submissions[0].comments
    )
    assert "rejected finding" not in blob
    assert "unverified finding" not in blob
    assert "Return value changed" in blob


def test_does_not_rederive_routing_from_finding_fields() -> None:
    github = FakeGitHub()
    finding = _finding(
        public_safe=True,
        verified=True,
        concern="correctness",
        title="looks public but the gate said no",
    )
    result = _post(
        github,
        [(finding, _decision(allow_public_post=False, confidentiality="restricted"))],
    )
    assert github.submissions == []
    assert result is None or result.github_review_id is None


def test_records_review_id_comment_ids_status_and_a_flat_event() -> None:
    events: list[tuple[str, dict[str, str | int]]] = []

    def record_event(_job_id: str, event_type: str, payload: dict[str, str | int]) -> None:
        events.append((event_type, payload))
        for value in payload.values():
            assert not isinstance(value, (dict, list))

    github = FakeGitHub()
    result = _post(github, [(_finding(), _decision())], record_event=record_event)
    assert result.github_review_id.startswith("rev-")
    assert result.response_status == 201
    assert events
    payload = events[-1][1]
    assert payload["github_review_id"] == result.github_review_id
    assert payload["response_status"] == 201
    assert "comment_count" in payload


def test_post_review_does_not_import_hosted_stores_or_reroute() -> None:
    source = (SRC_ROOT / "github" / "post_review.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = (
        "pr_reviewer.db",
        "pr_reviewer.events",
        "pr_reviewer.connectors",
        "pr_reviewer.notifications",
        "pr_reviewer.reviewer",
        "pr_reviewer.local_store",
        "route_finding",
    )
    for token in forbidden:
        assert token not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("pr_reviewer.db")
            assert not node.module.startswith("pr_reviewer.notifications")
            assert not node.module.startswith("pr_reviewer.reviewer")


def test_lifecycle_exports_the_pre_post_head_check() -> None:
    from pr_reviewer.github.lifecycle import reviewed_head_is_current

    assert reviewed_head_is_current(HEAD_SHA, HEAD_SHA) is True
    assert reviewed_head_is_current(HEAD_SHA, OTHER_SHA) is False


def test_hosted_connector_wrap_does_not_take_findings() -> None:
    import inspect

    from pr_reviewer.connectors.github import create_pull_request_review

    params = inspect.signature(create_pull_request_review).parameters
    assert "findings" not in params
    assert "head_sha" in params or "submission" in params
