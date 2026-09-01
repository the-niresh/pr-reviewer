"""Bare `reviewer` opens this Textual app instead of dumping usage."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Label


class ReviewerApp(App[None]):
    TITLE = "reviewer"

    def compose(self) -> ComposeResult:
        yield Label("reviewer")


def run_tui() -> int:
    ReviewerApp().run()
    return 0
