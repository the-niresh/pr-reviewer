"""Selecting a pull request starts a review from the terminal."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pr_reviewer.tui.github_reads import (
    FakeInstallationRepositoriesReader,
    FakeOpenPullRequestsReader,
    OpenPullRequest,
    PermittedRepository,
)
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission


def _connected_secrets(tmp_path: Path):
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
    secrets.set("model_key", "sk-test-model-key")
    return secrets


def test_selecting_a_pull_request_starts_a_review(tmp_path: Path) -> None:
    async def exercise() -> None:
        from pr_reviewer.tui.app import ReviewerApp
        from pr_reviewer.tui.screens.review import ReviewPanel

        repos = FakeInstallationRepositoriesReader(
            repositories=(PermittedRepository(id=11, full_name="acme/widgets"),)
        )
        prs = FakeOpenPullRequestsReader(
            pull_requests=(
                OpenPullRequest(
                    number=42,
                    title="Add widgets",
                    author="niresh",
                    head_sha="b" * 40,
                    updated_at="2026-09-02T12:00:00Z",
                ),
            )
        )
        app = ReviewerApp(
            secrets=_connected_secrets(tmp_path),
            installation_snapshot=InstallationSnapshot(
                github_login="the-niresh",
                github_user_id=42,
                installation_id=7010,
                repositories=(RepositoryPermission(11, "acme/widgets"),),
            ),
            repositories_reader=repos,
            pull_requests_reader=prs,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#repository-11")
            await pilot.pause()
            await pilot.click("#pull-request-42")
            review = app.query_one(ReviewPanel)
            assert review is not None
            nav = app.query_one("#section-nav")
            assert nav.current_section == "reviews"

    asyncio.run(exercise())


def test_empty_repository_list_is_distinct_from_empty_pull_requests() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        from pr_reviewer.tui.screens.repositories import RepositoriesPanel

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(
                    7010,
                    repositories_reader=FakeInstallationRepositoriesReader(),
                )

        async with Harness().run_test() as pilot:
            empty = str(pilot.app.query_one("#repositories-empty").render())
            assert "No repositories are permitted" in empty

        class HarnessPrs(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(
                    7010,
                    repositories_reader=FakeInstallationRepositoriesReader(
                        repositories=(PermittedRepository(id=11, full_name="acme/widgets"),)
                    ),
                    pull_requests_reader=FakeOpenPullRequestsReader(),
                )

        async with HarnessPrs().run_test() as pilot:
            await pilot.click("#repository-11")
            await pilot.pause()
            empty_prs = str(pilot.app.query_one("#pull-requests-empty").render())
            assert "No open pull requests" in empty_prs

    asyncio.run(exercise())
