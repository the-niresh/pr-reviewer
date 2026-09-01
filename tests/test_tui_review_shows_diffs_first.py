"""Starting a review shows every diff before any agent speaks."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission
from pr_reviewer.tui.screens.review import ReviewDiffItem, ReviewPanel

SAMPLE_DIFFS = (
    ReviewDiffItem("app.py", "@@ -1 +1 @@\n+return True"),
    ReviewDiffItem("README.md", "@@ -1 +1 @@\n+docs"),
)

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(RepositoryPermission(11, "in-scope"),),
)


def _connected_secrets(tmp_path: Path):
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
    secrets.set("model_key", "sk-test-model-key")
    return secrets


def test_review_panel_starts_with_diffs_and_hides_agents() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(SAMPLE_DIFFS)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            assert panel.phase == "diffs"
            assert panel.agents_visible is False
            assert pilot.app.query_one("#review-agents").display is False
            assert pilot.app.query_one("#review-diff-0") is not None
            assert pilot.app.query_one("#review-diff-1") is not None

    asyncio.run(exercise())


def test_review_panel_shows_every_diff_before_agents_speak() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(SAMPLE_DIFFS)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            first = str(panel.query_one("#review-diff-0").render())
            second = str(panel.query_one("#review-diff-1").render())
            assert "app.py" in first
            assert "README.md" in second
            assert panel.agents_visible is False
            from textual.widgets import Button

            panel.on_button_pressed(
                Button.Pressed(panel.query_one("#review-continue", Button))
            )
            assert panel.agents_visible is True
            assert pilot.app.query_one("#review-agents").display is True

    asyncio.run(exercise())


def test_connected_app_reviews_section_shows_diffs_first(tmp_path: Path) -> None:
    from pr_reviewer.tui.app import ReviewerApp

    async def exercise() -> None:
        app = ReviewerApp(
            secrets=_connected_secrets(tmp_path),
            installation_snapshot=SAMPLE_INSTALLATION,
        )
        async with app.run_test() as pilot:
            await pilot.click("#nav-reviews")
            panel = pilot.app.query_one(ReviewPanel)
            assert panel.phase == "diffs"
            assert panel.query_one("#review-diff-0") is not None
            assert panel.agents_visible is False

    asyncio.run(exercise())
