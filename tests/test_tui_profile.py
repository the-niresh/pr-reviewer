"""Profile screen for the signed-in GitHub identity."""

from __future__ import annotations

import asyncio

from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission
from pr_reviewer.tui.screens.profile import ProfilePanel

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(RepositoryPermission(github_repository_id=11, name="in-scope"),),
)


def test_profile_panel_shows_github_identity() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ProfilePanel(SAMPLE_INSTALLATION)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ProfilePanel)
            login = str(panel.query_one("#profile-login").render())
            user_id = str(panel.query_one("#profile-user-id").render())
            assert "the-niresh" in login
            assert "42" in user_id

    asyncio.run(exercise())
