"""Bare `reviewer` opens this Textual app instead of dumping usage."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from pr_reviewer.runner.secrets import SecretStore, get_secret_store
from pr_reviewer.tui.auth_state import is_github_connected
from pr_reviewer.tui.nav import SECTIONS, SectionNav, SectionSelected
from pr_reviewer.tui.pairing_client import PairingClient
from pr_reviewer.tui.screens.connect import ConnectPanel, can_start_review
from pr_reviewer.tui.theme import REVIEWER_CSS, REVIEWER_THEME


class ReviewerApp(App[None]):
    TITLE = "reviewer"
    CSS = REVIEWER_CSS

    def __init__(
        self,
        *,
        secrets: SecretStore | None = None,
        pairing_client: PairingClient | None = None,
    ) -> None:
        super().__init__()
        self.register_theme(REVIEWER_THEME)
        self.theme = REVIEWER_THEME.name
        self._secrets = secrets or get_secret_store(
            file_fallback_directory=Path.home() / ".config" / "pr-reviewer"
        )
        self._pairing_client = pairing_client

    @property
    def github_connected(self) -> bool:
        return is_github_connected(self._secrets)

    def compose(self) -> ComposeResult:
        if self.github_connected:
            yield Horizontal(
                SectionNav(id="section-nav"),
                Static(SECTIONS[0], id="section-content"),
                id="main-layout",
            )
            return

        yield Horizontal(
            SectionNav(id="section-nav"),
            ConnectPanel(pairing_client=self._pairing_client, id="connect-screen"),
            id="main-layout",
        )

    def on_section_selected(self, message: SectionSelected) -> None:
        if message.section_id == "reviews" and not can_start_review(self.github_connected):
            self.notify("Connect GitHub before starting a review.", severity="warning")
            return
        if self.github_connected:
            self.query_one("#section-content", Static).update(message.section_id)


def run_tui() -> int:
    ReviewerApp().run()
    return 0
