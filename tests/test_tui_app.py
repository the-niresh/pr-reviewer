"""Bare `reviewer` opens the Textual TUI instead of dumping usage."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


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
