"""Four-section TUI navigation with a persistent current-section indicator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pr_reviewer.tui.app import ReviewerApp
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission
from pr_reviewer.tui.nav import SECTIONS, SectionNav

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(RepositoryPermission(11, "in-scope"),),
)




def make_connected_app(tmp_path: Path):

    return ReviewerApp(
        secrets=connected_secrets(tmp_path),
        installation_snapshot=SAMPLE_INSTALLATION,
    )


def connected_secrets(tmp_path: Path):
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
    secrets.set("model_key", "sk-test-model-key")
    return secrets


@pytest.mark.parametrize("section_id", SECTIONS)
def test_section_ids_are_stable(section_id: str) -> None:
    assert section_id in {"repositories", "agent-prompts", "profile", "reviews"}


def test_section_nav_lists_four_sections() -> None:
    nav = SectionNav()
    assert nav.section_ids == list(SECTIONS)
    assert len(nav.section_ids) == 4


def test_reviewer_app_starts_on_repositories(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test() as pilot:
            nav = app.query_one(SectionNav)
            assert nav.current_section == "repositories"
            assert pilot.app.query_one("#repositories-heading") is not None

    asyncio.run(exercise())


def test_current_section_is_visually_distinct_without_focus(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test() as pilot:
            nav = app.query_one(SectionNav)
            current = nav.query_one("#nav-repositories")
            assert "nav-item--current" in current.classes
            profile = nav.query_one("#nav-profile")
            assert "nav-item--current" not in profile.classes

            await pilot.press("tab")
            assert "nav-item--current" in current.classes
            assert "nav-item--current" not in profile.classes

    asyncio.run(exercise())


def test_selecting_a_section_updates_content_and_indicator(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test() as pilot:
            await pilot.click("#nav-reviews")
            nav = app.query_one(SectionNav)
            assert nav.current_section == "reviews"
            assert pilot.app.query_one("#section-placeholder") is not None
            assert str(pilot.app.query_one("#section-placeholder").render()) == "reviews"
            reviews = nav.query_one("#nav-reviews")
            repositories = nav.query_one("#nav-repositories")
            assert "nav-item--current" in reviews.classes
            assert "nav-item--current" not in repositories.classes

    asyncio.run(exercise())
