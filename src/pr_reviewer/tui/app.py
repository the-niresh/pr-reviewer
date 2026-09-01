"""Bare `reviewer` opens this Textual app instead of dumping usage."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from pr_reviewer.tui.nav import SECTIONS, SectionNav, SectionSelected
from pr_reviewer.tui.theme import REVIEWER_CSS, REVIEWER_THEME


class ReviewerApp(App[None]):
    TITLE = "reviewer"
    CSS = REVIEWER_CSS

    def __init__(self) -> None:
        super().__init__()
        self.register_theme(REVIEWER_THEME)
        self.theme = REVIEWER_THEME.name

    def compose(self) -> ComposeResult:
        yield Horizontal(
            SectionNav(id="section-nav"),
            Static(SECTIONS[0], id="section-content"),
            id="main-layout",
        )

    def on_section_selected(self, message: SectionSelected) -> None:
        self.query_one("#section-content", Static).update(message.section_id)


def run_tui() -> int:
    ReviewerApp().run()
    return 0
