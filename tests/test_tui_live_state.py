"""The TUI stays open and reflects runner state live, without a restart (phase 22).

Boots one ReviewerApp instance and drives two sequential PR sync events through the
same running app/pilot. A test that only checks the initial render proves nothing about
staying live - this asserts the screen keeps reflecting new runner state as it arrives,
with no second ReviewerApp construction and no second run_test() anywhere in the test.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from textual.notifications import SeverityLevel
from textual.pilot import Pilot

from pr_reviewer.tui.auto_review import PullRequestSyncEvent
from pr_reviewer.tui.github_reads import FakeInstallationRepositoriesReader, PermittedRepository
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot, RepositoryPermission

if TYPE_CHECKING:
    from pr_reviewer.runner.secrets import FileSecretStore

SAMPLE_INSTALLATION = InstallationSnapshot(
    github_login="the-niresh",
    github_user_id=42,
    installation_id=7010,
    repositories=(RepositoryPermission(11, "in-scope"),),
)

HEAD_SHA = "b" * 40
NEWER_HEAD_SHA = "c" * 40
WAIT_TIMEOUT_SECONDS = 2.0


def _connected_secrets(tmp_path: Path) -> FileSecretStore:
    from pr_reviewer.runner.secrets import FileSecretStore

    secrets = FileSecretStore(tmp_path)
    secrets.set("runner_credential", "test-runner-credential")
    secrets.set("model_key", "sk-test-model-key")
    return secrets


class _FakeAutoReviewEventSource:
    def __init__(self) -> None:
        self._pending: list[PullRequestSyncEvent] = []

    def push(self, event: PullRequestSyncEvent) -> None:
        self._pending.append(event)

    def poll(self) -> list[PullRequestSyncEvent]:
        batch = self._pending
        self._pending = []
        return batch


async def wait_until(
    pilot: Pilot[Any],
    condition: Callable[[], bool],
    *,
    description: str,
    timeout: float = WAIT_TIMEOUT_SECONDS,
) -> None:
    """Pump the Textual event loop until `condition` holds or `timeout` elapses.

    Same shape as tests/test_tui_auto_review.py's helper: loop on the observable
    condition itself, with a hard deadline that fails loudly, rather than guessing a
    number of blind pauses.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await pilot.pause()
    raise AssertionError(f"timed out after {timeout}s waiting for {description}")


def test_tui_reflects_pr_events_live_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pr_reviewer.tui.app import ReviewerApp
    from pr_reviewer.tui.nav import SectionNav
    from pr_reviewer.tui.screens.review import ReviewPanel

    source = _FakeAutoReviewEventSource()
    notified: list[str] = []

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
        original_notify = app.notify

        def recording_notify(
            message: str,
            *,
            title: str = "",
            severity: SeverityLevel = "information",
            timeout: float | None = None,
            markup: bool = True,
        ) -> None:
            notified.append(message)
            original_notify(
                message, title=title, severity=severity, timeout=timeout, markup=markup
            )

        monkeypatch.setattr(app, "notify", recording_notify)

        async with app.run_test() as pilot:
            nav = app.query_one("#section-nav", SectionNav)

            def default_section_settled() -> bool:
                return bool(app.query("#repository-11")) or bool(app.query("#repositories-empty"))

            await wait_until(
                pilot,
                default_section_settled,
                description="the default repositories section to finish mounting",
            )

            # A real initial state, distinct from what we are about to drive it to -
            # otherwise "stays live" is unfalsifiable.
            assert nav.current_section == "repositories"
            assert not app.query(ReviewPanel)

            source.push(
                PullRequestSyncEvent(action="opened", pull_request_number=12, head_sha=HEAD_SHA)
            )

            def opened_review_visible() -> bool:
                return nav.current_section == "reviews" and bool(app.query(ReviewPanel))

            await wait_until(
                pilot,
                opened_review_visible,
                description="the opened PR to appear as a live review",
            )
            assert notified == ["Reviewing PR #12"]

            # Drive a second, distinct runner state change through the same running
            # app and pilot - no second ReviewerApp, no second run_test() - and
            # confirm it is reflected too.
            source.push(
                PullRequestSyncEvent(
                    action="synchronize", pull_request_number=12, head_sha=NEWER_HEAD_SHA
                )
            )

            await wait_until(
                pilot,
                lambda: len(notified) == 2,
                description="the synchronize event to supersede the running review",
            )
            assert notified[-1] == "Reviewing PR #12 (superseded previous run)"
            assert nav.current_section == "reviews"
            assert app.query(ReviewPanel)

    asyncio.run(exercise())
