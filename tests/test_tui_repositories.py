"""Repositories screen lists live permitted repositories."""

from __future__ import annotations

import asyncio

import pytest

from pr_reviewer.tui import github_reads
from pr_reviewer.tui.github_connect import HostedOriginError
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


def test_repositories_panel_says_so_when_not_paired_instead_of_showing_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing runner credential (or hosted origin) is a different fact from "this
    installation has zero repositories" and must render as a different, visible message --
    never fall through to the same empty-list widget a genuine empty result would use.
    """

    def raise_hosted_origin_error() -> str:
        raise HostedOriginError("PR_REVIEWER_HOSTED_ORIGIN is not set")

    monkeypatch.setattr(github_reads, "resolved_hosted_origin", raise_hosted_origin_error)

    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield RepositoriesPanel(7010)

        async with Harness().run_test() as pilot:
            await pilot.pause()
            assert not pilot.app.query("#repositories-empty")
            message = str(pilot.app.query_one("#repositories-unavailable").render())
            assert "hosted plane" in message.lower()

    asyncio.run(exercise())
