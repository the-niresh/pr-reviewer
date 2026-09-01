"""Repositories screen listing installation-permitted repositories."""

from __future__ import annotations

import asyncio
from pathlib import Path

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


def test_repositories_panel_shows_persisted_policy(tmp_path: Path) -> None:
    from textual.app import App, ComposeResult

    from pr_reviewer.local_store.repo_config import RepoConfigStore
    from pr_reviewer.security.instruction_sources import ReviewPolicy

    store = RepoConfigStore(tmp_path / "repo_config.json")
    store.set(11, ReviewPolicy(instructions_enabled=True, specialist_mode=True))

    async def exercise() -> None:
        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(SAMPLE_INSTALLATION, repo_config=store)

        async with Harness().run_test() as pilot:
            row = str(pilot.app.query_one("#repo-11").render())
            assert "instructions" in row
            assert "specialists" in row

    asyncio.run(exercise())


def test_repositories_panel_shows_saved_model_choice(tmp_path: Path) -> None:
    from textual.app import App, ComposeResult

    from pr_reviewer.local_store.repo_config import RepoConfigStore, RepoModelChoice

    store = RepoConfigStore(tmp_path / "repo_config.json")
    store.set_model_choice(
        11,
        RepoModelChoice(provider_id="openai", model_id="gpt-4o-mini"),
    )

    async def exercise() -> None:
        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(SAMPLE_INSTALLATION, repo_config=store)

        async with Harness().run_test() as pilot:
            summary = str(pilot.app.query_one("#repo-model-summary-11").render())
            assert "openai/gpt-4o-mini" in summary

    asyncio.run(exercise())


def test_repositories_panel_persists_provider_change(tmp_path: Path) -> None:
    from textual.app import App, ComposeResult
    from textual.widgets import Select

    from pr_reviewer.local_store.repo_config import RepoConfigStore

    store = RepoConfigStore(tmp_path / "repo_config.json")

    async def exercise() -> None:
        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(SAMPLE_INSTALLATION, repo_config=store)

        async with Harness().run_test() as pilot:
            provider = pilot.app.query_one("#repo-provider-11", Select)
            provider.value = "anthropic"
            panel = pilot.app.query_one(RepositoriesPanel)
            panel.on_select_changed(Select.Changed(provider, "anthropic"))
            saved = store.get_model_choice(11)
            assert saved.provider_id == "anthropic"
            summary = str(pilot.app.query_one("#repo-model-summary-11").render())
            assert summary.startswith("anthropic/")

    asyncio.run(exercise())
