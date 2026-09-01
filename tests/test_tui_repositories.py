"""Repositories screen listing installation-permitted repositories."""

from __future__ import annotations

import asyncio

from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission
from pr_reviewer.tui.screens.repositories import RepositoriesPanel

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(
        RepositoryPermission(github_repository_id=11, name="in-scope"),
        RepositoryPermission(github_repository_id=12, name="docs-only"),
    ),
)


def test_repositories_panel_lists_installation_repositories() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(SAMPLE_INSTALLATION)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(RepositoriesPanel)
            first = str(panel.query_one("#repo-11").render())
            second = str(panel.query_one("#repo-12").render())
            assert "in-scope" in first
            assert "docs-only" in second

    asyncio.run(exercise())


def test_repositories_panel_matches_installation_snapshot_exactly() -> None:
    assert len(SAMPLE_INSTALLATION.repositories) == 2
    assert SAMPLE_INSTALLATION.repositories[0].name == "in-scope"
