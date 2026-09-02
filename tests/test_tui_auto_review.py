"""Auto-review while the Textual TUI is running (phase 26 task 26.4)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from textual.pilot import Pilot

from pr_reviewer.tui.auto_review import (
    TUI_CLOSED_AUTO_REVIEW_MESSAGE,
    AutoReviewCoordinator,
    PullRequestSyncEvent,
)
from pr_reviewer.tui.github_reads import FakeInstallationRepositoriesReader, PermittedRepository
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission

if TYPE_CHECKING:
    from pr_reviewer.runner.secrets import FileSecretStore

WAIT_TIMEOUT_SECONDS = 2.0


async def wait_until(
    pilot: Pilot[Any],
    condition: Callable[[], bool],
    *,
    description: str,
    timeout: float = WAIT_TIMEOUT_SECONDS,
) -> None:
    """Pump the Textual event loop until `condition` holds or `timeout` elapses.

    A bare `pilot.pause()` only proves a queued message was processed, not that the
    condition it was meant to produce actually landed - that gap is what made this test
    flaky. Looping on the observable condition itself removes the race entirely.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await pilot.pause()
    raise AssertionError(f"timed out after {timeout}s waiting for {description}")

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(RepositoryPermission(11, "in-scope"),),
)

HEAD_SHA = "b" * 40
NEWER_HEAD_SHA = "c" * 40


def _connected_secrets(tmp_path: Path) -> FileSecretStore:
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
    secrets.set("model_key", "sk-test-model-key")
    return secrets


class FakeAutoReviewEventSource:
    def __init__(self) -> None:
        self._pending: list[PullRequestSyncEvent] = []

    def push(self, event: PullRequestSyncEvent) -> None:
        self._pending.append(event)

    def poll(self) -> list[PullRequestSyncEvent]:
        batch = self._pending
        self._pending = []
        return batch


def _opened_event(
    *,
    pull_request_number: int = 12,
    head_sha: str = HEAD_SHA,
) -> PullRequestSyncEvent:
    return PullRequestSyncEvent(
        action="opened",
        pull_request_number=pull_request_number,
        head_sha=head_sha,
    )


def test_coordinator_ignores_events_when_not_running() -> None:
    coordinator = AutoReviewCoordinator()
    outcome = coordinator.handle(_opened_event())
    assert outcome.kind == "not_running"


def test_opened_pr_starts_review_when_running() -> None:
    started: list[tuple[int, str, bool]] = []

    def on_start(event: PullRequestSyncEvent, superseded: bool, _previous: str) -> None:
        started.append((event.pull_request_number, event.head_sha, superseded))

    coordinator = AutoReviewCoordinator(on_start_review=on_start)
    coordinator.start()
    outcome = coordinator.handle(_opened_event())
    assert outcome.kind == "started"
    assert started == [(12, HEAD_SHA, False)]


def test_synchronize_supersedes_previous_head() -> None:
    started: list[tuple[int, str, bool]] = []

    def on_start(event: PullRequestSyncEvent, superseded: bool, _previous: str) -> None:
        started.append((event.pull_request_number, event.head_sha, superseded))

    coordinator = AutoReviewCoordinator(on_start_review=on_start)
    coordinator.start()
    coordinator.handle(_opened_event())
    outcome = coordinator.handle(
        PullRequestSyncEvent(
            action="synchronize",
            pull_request_number=12,
            head_sha=NEWER_HEAD_SHA,
        )
    )
    assert outcome.kind == "superseded"
    assert outcome.previous_head_sha == HEAD_SHA
    assert started[-1] == (12, NEWER_HEAD_SHA, True)


def test_stop_returns_closed_message() -> None:
    coordinator = AutoReviewCoordinator()
    coordinator.start()
    message = coordinator.stop()
    assert message == TUI_CLOSED_AUTO_REVIEW_MESSAGE
    assert coordinator.handle(_opened_event()).kind == "not_running"


def test_run_tui_prints_closed_message_when_auto_review_was_running(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pr_reviewer.tui import app as app_module

    class FakeApp:
        _auto_review_was_running = True

        def run(self) -> None:
            return None

    monkeypatch.setattr(app_module, "ReviewerApp", FakeApp)
    app_module.run_tui()
    captured = capsys.readouterr()
    assert TUI_CLOSED_AUTO_REVIEW_MESSAGE in captured.err


def test_tui_polls_events_and_opens_review_section(tmp_path: Path) -> None:
    from textual.widgets import Select

    from pr_reviewer.tui.app import ReviewerApp
    from pr_reviewer.tui.nav import SectionNav
    from pr_reviewer.tui.screens.review import ReviewPanel

    source = FakeAutoReviewEventSource()

    async def exercise() -> None:
        app = ReviewerApp(
            secrets=_connected_secrets(tmp_path),
            installation_snapshot=SAMPLE_INSTALLATION,
            repositories_reader=FakeInstallationRepositoriesReader(
                repositories=(PermittedRepository(11, "acme/in-scope"),)
            ),
            auto_review_event_source=source,
            auto_review_poll_interval=0.01,
        )
        async with app.run_test() as pilot:
            nav = app.query_one("#section-nav", SectionNav)

            def default_section_settled() -> bool:
                return bool(app.query("#repository-11")) or bool(app.query("#repositories-empty"))

            await wait_until(
                pilot,
                default_section_settled,
                description="the default repositories section to finish mounting",
            )

            source.push(_opened_event())

            def review_section_open() -> bool:
                return nav.current_section == "reviews" and bool(app.query(ReviewPanel))

            await wait_until(
                pilot,
                review_section_open,
                description="the auto-review poll to open the reviews section",
            )

            review = app.query_one(ReviewPanel)
            assert review is not None
            assert nav.current_section == "reviews"

    asyncio.run(exercise())
