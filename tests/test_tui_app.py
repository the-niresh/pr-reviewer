"""Bare `reviewer` opens the Textual TUI instead of dumping usage."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission
from pr_reviewer.tui.nav import SECTIONS
from pr_reviewer.tui.theme import REVIEWER_THEME

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(RepositoryPermission(11, "in-scope"),),
)




def make_connected_app(tmp_path: Path):
    from pr_reviewer.tui.app import ReviewerApp

    return ReviewerApp(
        secrets=connected_secrets(tmp_path),
        installation_snapshot=SAMPLE_INSTALLATION,
    )


def connected_secrets(tmp_path: Path):
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
    secrets.set("model_key", "sk-test-model-key")
    return secrets


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


def test_reviewer_app_registers_custom_theme(tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test():
            assert app.theme == "reviewer"
            assert "reviewer" in app.available_themes

    asyncio.run(exercise())


@pytest.mark.parametrize("section_id", SECTIONS)
def test_each_section_screen_renders_headless(section_id: str, tmp_path: Path) -> None:
    async def exercise() -> None:
        app = make_connected_app(tmp_path)
        async with app.run_test() as pilot:
            await pilot.click(f"#nav-{section_id}")
            if section_id == "profile":
                assert pilot.app.query_one("#profile-login") is not None
            elif section_id == "repositories":
                assert pilot.app.query_one("#repositories-heading") is not None
            else:
                placeholder = pilot.app.query_one("#section-placeholder")
                assert str(placeholder.render()) == section_id

    asyncio.run(exercise())
