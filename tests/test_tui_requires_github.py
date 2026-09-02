"""Unconnected TUI shows GitHub connect and refuses reviews."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult

from pr_reviewer.runner.secrets import FileSecretStore
from pr_reviewer.tui.app import ReviewerApp
from pr_reviewer.tui.screens.connect import ConnectPanel, can_start_review


class ConnectHarness(App[None]):
    def __init__(self, panel: ConnectPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel



class FakePairingClient:
    def __init__(self, *, status_sequence: list[str] | None = None) -> None:
        self.status_sequence = list(status_sequence or ["pending"])
        self.create_calls: list[tuple[str, str]] = []
        self.status_calls: list[tuple[str, str]] = []

    def create_code(self, device_name: str, challenge: str) -> str:
        self.create_calls.append((device_name, challenge))
        return "PAIR-TUI-1"

    def status(self, code: str, challenge: str) -> str:
        self.status_calls.append((code, challenge))
        if self.status_sequence:
            return self.status_sequence.pop(0)
        return "pending"

    def exchange(self, code: str, proof: str) -> str:
        return "runner-credential-test"


def test_can_start_review_requires_connection() -> None:
    assert can_start_review(False) is False
    assert can_start_review(True, model_key_present=False) is False
    assert can_start_review(True, model_key_present=True) is True


def test_unconnected_app_shows_connect_screen() -> None:
    async def exercise() -> None:
        secrets = FileSecretStore(Path("/tmp/pr-reviewer-tui-secrets"))
        app = ReviewerApp(secrets=secrets, pairing_client=FakePairingClient())
        async with app.run_test():
            assert app.query_one("#connect-screen", ConnectPanel) is not None
            assert app.github_connected is False

    asyncio.run(exercise())


def test_reviews_section_is_refused_when_github_is_not_connected() -> None:
    async def exercise() -> None:
        secrets = FileSecretStore(Path("/tmp/pr-reviewer-tui-secrets-refuse"))
        app = ReviewerApp(secrets=secrets, pairing_client=FakePairingClient())
        async with app.run_test() as pilot:
            await pilot.click("#nav-reviews")
            refusal = app.query_one("#connect-refusal")
            assert "no review" in str(refusal.render()).lower()

    asyncio.run(exercise())
