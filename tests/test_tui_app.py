"""Bare `reviewer` opens the Textual TUI instead of dumping usage."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from pr_reviewer.tui.nav import SECTIONS
from pr_reviewer.tui.theme import REVIEWER_THEME


def test_reviewer_app_is_a_textual_app() -> None:
    from textual.app import App

    from pr_reviewer.tui.app import ReviewerApp

    assert issubclass(ReviewerApp, App)


def test_bare_reviewer_on_a_tty_opens_the_tui(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pr_reviewer.reviewer_entry import main as reviewer_main

    calls: list[str] = []

    def fake_run_tui() -> int:
        calls.append("tui")
        return 0

    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("pr_reviewer.tui.app.run_tui", fake_run_tui)
    code = reviewer_main([])
    assert code == 0
    assert calls == ["tui"]
    captured = capsys.readouterr()
    assert "usage:" not in captured.err.lower()


def test_bare_reviewer_without_a_tty_does_not_start_the_tui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pr_reviewer.reviewer_entry import main as reviewer_main

    calls: list[str] = []

    def fake_run_tui() -> int:
        calls.append("tui")
        return 0

    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr("pr_reviewer.tui.app.run_tui", fake_run_tui)
    code = reviewer_main([])
    assert code == 1
    assert calls == []


def test_reviewer_theme_uses_deliberate_colours() -> None:
    assert REVIEWER_THEME.name == "reviewer"
    assert REVIEWER_THEME.background == "#0f172a"
    assert REVIEWER_THEME.primary == "#38bdf8"


def test_reviewer_app_registers_custom_theme() -> None:
    async def exercise() -> None:
        from pr_reviewer.tui.app import ReviewerApp

        app = ReviewerApp()
        async with app.run_test():
            assert app.theme == "reviewer"
            assert "reviewer" in app.available_themes

    asyncio.run(exercise())


@pytest.mark.parametrize("section_id", SECTIONS)
def test_each_section_screen_renders_headless(section_id: str) -> None:
    async def exercise() -> None:
        from pr_reviewer.tui.app import ReviewerApp

        app = ReviewerApp()
        async with app.run_test() as pilot:
            await pilot.click(f"#nav-{section_id}")
            content = pilot.app.query_one("#section-content")
            assert str(content.render()) == section_id

    asyncio.run(exercise())
