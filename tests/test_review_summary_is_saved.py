"""Sending side of review summary push."""

from __future__ import annotations

from pr_reviewer.tui.push_review_summary import (
    ReviewFindingSummary,
    ReviewSummaryPush,
    build_summary_payload,
    push_review_summary,
)


class RecordingClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.should_fail = False

    def push(self, payload: dict[str, object]) -> None:
        if self.should_fail:
            raise RuntimeError("hosted plane unavailable")
        self.payloads.append(payload)


def test_build_summary_payload_uses_an_allowlist() -> None:
    summary = ReviewSummaryPush(
        review_job_id="job-1",
        installation_id=7010,
        github_repository_id=11,
        pull_request_number=42,
        head_sha="a" * 40,
        status="completed",
        findings=(
            ReviewFindingSummary(
                concern="security",
                severity="high",
                file_path="app.py",
                line_start=1,
                line_end=2,
                title="Leak",
                status="posted",
            ),
        ),
    )
    payload = build_summary_payload(summary)
    assert set(payload) == {
        "review_job_id",
        "installation_id",
        "github_repository_id",
        "pull_request_number",
        "head_sha",
        "status",
        "stopped_early",
        "findings",
    }
    assert "reasoning" not in payload


def test_push_payload_never_includes_reasoning() -> None:
    client = RecordingClient()
    push_review_summary(
        client,
        ReviewSummaryPush(
            review_job_id="job-1",
            installation_id=1,
            github_repository_id=2,
            pull_request_number=3,
            head_sha="b" * 40,
            status="completed",
        ),
    )
    assert client.payloads
    assert "reasoning" not in client.payloads[0]


def test_failed_push_does_not_raise() -> None:
    client = RecordingClient()
    client.should_fail = True
    result = push_review_summary(
        client,
        ReviewSummaryPush(
            review_job_id="job-1",
            installation_id=1,
            github_repository_id=2,
            pull_request_number=3,
            head_sha="c" * 40,
            status="completed",
        ),
    )
    assert result.ok is False
    assert client.payloads == []
