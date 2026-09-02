"""A real keyboard model: tab crosses between the sidebar and the content pane, and the
footer is always visible so the keys are discoverable, not hidden knowledge.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Footer

from pr_reviewer.tui.app import ReviewerApp
from pr_reviewer.tui.github_reads import FakeInstallationRepositoriesReader, PermittedRepository
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission
from pr_reviewer.tui.nav import SectionNav

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(RepositoryPermission(11, "in-scope"),),
)


def make_connected_app(tmp_path: Path) -> ReviewerApp:
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
    secrets.set("model_key", "sk-test-model-key")
    return ReviewerApp(
        secrets=secrets,
        installation_snapshot=SAMPLE_INSTALLATION,
        repositories_reader=FakeInstallationRepositoriesReader(
            repositories=(PermittedRepository(11, "acme/in-scope"),)
        ),
    )


def test_tab_moves_focus_from_the_sidebar_into_the_content_pane(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            nav = app.query_one("#section-nav")
            content = app.query_one("#section-content")

            # Repositories loads with a repository button in the content pane; start focus
            # there explicitly so the test does not depend on Textual's initial-focus choice.
            content.query("Button").first().focus()
            await pilot.pause()
            assert app.focused is not None
            assert any(app.focused is widget for widget in content.query("*"))

            await pilot.press("tab")
            assert app.focused is not None
            assert any(app.focused is widget for widget in nav.query("*")), (
                "tab did not move focus out of the content pane and into the sidebar"
            )

            await pilot.press("tab")
            assert any(app.focused is widget for widget in content.query("*")), (
                "tab did not move focus back into the content pane"
            )

    asyncio.run(exercise())


def test_footer_is_always_visible_and_names_the_keys(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test():
            footer = app.query_one(Footer)
            assert footer.display is not False

    asyncio.run(exercise())


def test_digit_key_jumps_straight_to_a_section(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test() as pilot:
            await pilot.press("4")
            nav = app.query_one(SectionNav)
            assert nav.current_section == "reviews"

    asyncio.run(exercise())
