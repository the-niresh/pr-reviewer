"""TUI and hosted list share the same saved review record shape."""

from __future__ import annotations

from pr_reviewer.tui.push_review_summary import (
    ReviewFindingSummary,
    ReviewSummaryPush,
    build_summary_payload,
)


def test_tui_payload_matches_the_hosted_summary_record() -> None:
    summary = ReviewSummaryPush(
        review_job_id="job-parity",
        installation_id=7010,
        github_repository_id=11,
        pull_request_number=7,
        head_sha="d" * 40,
        status="completed",
        findings=(
            ReviewFindingSummary(
                concern="tests",
                severity="medium",
                file_path="tests/test_app.py",
                line_start=4,
                line_end=4,
                title="Missing test",
                status="posted",
            ),
        ),
    )
    payload = build_summary_payload(summary)
    assert payload["review_job_id"] == "job-parity"
    assert payload["findings"][0]["title"] == "Missing test"
