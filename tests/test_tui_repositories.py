"""Repositories screen lists live permitted repositories."""

from __future__ import annotations

import asyncio

from pr_reviewer.tui.github_reads import (
    FakeInstallationRepositoriesReader,
    PermittedRepository,
)
from pr_reviewer.tui.screens.repositories import RepositoriesPanel


def test_repositories_panel_lists_live_repositories() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        reader = FakeInstallationRepositoriesReader(
            repositories=(
                PermittedRepository(id=11, full_name="acme/in-scope"),
                PermittedRepository(id=12, full_name="acme/docs-only"),
            )
        )

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(7010, repositories_reader=reader)

        async with Harness().run_test() as pilot:
            await pilot.pause()
            first = str(pilot.app.query_one("#repository-11").render())
            second = str(pilot.app.query_one("#repository-12").render())
            assert "acme/in-scope" in first
            assert "acme/docs-only" in second

    asyncio.run(exercise())
