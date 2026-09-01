"""Four-section TUI navigation with a persistent current-section indicator."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pr_reviewer.tui.app import ReviewerApp
from pr_reviewer.tui.nav import SECTIONS, SectionNav


def connected_secrets(tmp_path: Path):
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
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
        app = ReviewerApp(secrets=connected_secrets(tmp_path))
        async with app.run_test() as pilot:
            nav = app.query_one(SectionNav)
            assert nav.current_section == "repositories"
            content = pilot.app.query_one("#section-content")
            assert str(content.render()) == "repositories"

    asyncio.run(exercise())


def test_current_section_is_visually_distinct_without_focus(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = ReviewerApp(secrets=connected_secrets(tmp_path))
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
        app = ReviewerApp(secrets=connected_secrets(tmp_path))
        async with app.run_test() as pilot:
            await pilot.click("#nav-reviews")
            nav = app.query_one(SectionNav)
            assert nav.current_section == "reviews"
            content = pilot.app.query_one("#section-content")
            assert str(content.render()) == "reviews"
            reviews = nav.query_one("#nav-reviews")
            repositories = nav.query_one("#nav-repositories")
            assert "nav-item--current" in reviews.classes
            assert "nav-item--current" not in repositories.classes

    asyncio.run(exercise())
