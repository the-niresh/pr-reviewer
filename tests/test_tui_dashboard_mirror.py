from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from pr_reviewer.tui.review_dashboard import (
    DashboardFinding,
    DashboardRepository,
    DashboardReview,
    ReviewDashboardPanel,
)


def _widget_text(widget: Any) -> str:
    return str(widget.render())


def _review(
    *,
    review_id: str,
    status: str = "completed",
    stopped_early: bool = False,
    severity: str = "high",
) -> DashboardReview:
    return DashboardReview(
        review_job_id=review_id,
        pull_request_number=7,
        head_sha="d" * 40,
        status=status,
        stopped_early=stopped_early,
        stopped_early_message=(
            "This review stopped early: the provider ran out of tokens partway through."
            if stopped_early
            else None
        ),
        created_at=datetime(2026, 9, 3, 8, 0, tzinfo=UTC),
        findings=(
            DashboardFinding(
                concern="tests",
                severity=severity,
                file_path="tests/test_app.py",
                line_start=4,
                line_end=4,
                title="Missing test",
                status="posted",
            ),
        ),
    )


def test_terminal_dashboard_shows_overview_table_and_detail() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewDashboardPanel(
                    (
                        DashboardRepository(
                            installation_id=1,
                            github_repository_id=2,
                            repository_name="acme/widgets",
                            reviews=(_review(review_id="review-1"),),
                        ),
                    )
                )

        async with Harness().run_test() as pilot:
            overview = _widget_text(pilot.app.query_one("#review-dashboard-overview"))
            assert "Reviews: 1" in overview
            assert "Findings: 1" in overview
            row = pilot.app.query_one("#review-row-review-1")
            assert "acme/widgets" in str(row.label)
            assert "HIGH severity" in str(row.label)
            row.focus()
            await pilot.press("enter")
            assert _widget_text(pilot.app.query_one("#review-detail-title")) == "PR #7"
            findings = _widget_text(pilot.app.query_one("#review-detail-findings"))
            assert "tests/test_app.py:4-4" in findings

    asyncio.run(exercise())


def test_terminal_dashboard_marks_stopped_early_as_not_complete() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewDashboardPanel(
                    (
                        DashboardRepository(
                            installation_id=1,
                            github_repository_id=2,
                            repository_name="acme/widgets",
                            reviews=(
                                _review(
                                    review_id="review-2",
                                    status="stopped_early",
                                    stopped_early=True,
                                    severity="medium",
                                ),
                            ),
                        ),
                    )
                )

        async with Harness().run_test() as pilot:
            row = pilot.app.query_one("#review-row-review-2")
            assert "Stopped early" in str(row.label)
            assert "completed" not in str(row.label).lower()
            row.focus()
            await pilot.press("enter")
            status = _widget_text(pilot.app.query_one("#review-detail-status"))
            assert "Stopped early" in status
            assert "provider ran out of tokens" in status

    asyncio.run(exercise())
