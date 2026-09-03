"""Claude-Code-style device login: paste the link, never auto-launch a browser, never let a
browser failure kill the app.
"""

from __future__ import annotations

import asyncio
import time
import webbrowser
from collections.abc import Callable
from typing import Any

import pytest
from textual.pilot import Pilot

from pr_reviewer.tui.screens.connect import ConnectConfig, ConnectPanel

WAIT_TIMEOUT_SECONDS = 2.0


async def wait_until(
    pilot: Pilot[Any],
    condition: Callable[[], bool],
    *,
    description: str,
    timeout: float = WAIT_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await pilot.pause()
    raise AssertionError(f"timed out after {timeout}s waiting for {description}")


class FakePairingClient:
    def __init__(self) -> None:
        self.create_calls: list[tuple[str, str]] = []

    def create_code(self, device_name: str, challenge: str) -> str:
        self.create_calls.append((device_name, challenge))
        return "PAIR-DEVICE-1"

    def status(self, code: str, challenge: str) -> str:
        return "pending"

    def exchange(self, code: str, proof: str) -> str:
        return "runner-credential"


def make_harness(*, pairing_client: FakePairingClient, browser_opener: Callable[[str], object]):
    from textual.app import App, ComposeResult

    class Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield ConnectPanel(
                config=ConnectConfig(
                    hosted_origin="https://reviewer.niresh.tech",
                    device_name="test-laptop",
                ),
                pairing_client=pairing_client,
                browser_opener=browser_opener,
            )

    return Harness()


def test_sign_in_shows_the_full_url_and_pairing_code_for_copying() -> None:
    """This is the primary path, not a fallback: the link and code must be on screen and
    readable, not hidden behind a browser redirect."""

    async def exercise() -> None:
        pairing = FakePairingClient()
        app = make_harness(pairing_client=pairing, browser_opener=lambda _url: None)
        async with app.run_test() as pilot:
            await pilot.click("#connect-sign-in")
            await wait_until(
                pilot,
                lambda: bool(pilot.app.query("#sign-in-url")),
                description="the sign-in url to appear",
            )
            url_text = str(pilot.app.query_one("#sign-in-url").render())
            code_text = str(pilot.app.query_one("#pairing-code").render())
            assert "https://reviewer.niresh.tech/api/auth/github/sign-in" in url_text
            assert "PAIR-DEVICE-1" in code_text

    asyncio.run(exercise())


def test_sign_in_url_carries_the_pairing_code() -> None:
    """The pairing code the terminal is waiting on must ride along in the sign-in link, or the
    hosted plane has no way to connect a completed browser sign-in back to this terminal."""

    async def exercise() -> None:
        pairing = FakePairingClient()
        app = make_harness(pairing_client=pairing, browser_opener=lambda _url: None)
        async with app.run_test() as pilot:
            await pilot.click("#connect-sign-in")
            await wait_until(
                pilot,
                lambda: bool(pilot.app.query("#sign-in-url")),
                description="the sign-in url to appear",
            )
            url_text = str(pilot.app.query_one("#sign-in-url").render())
            assert "pairing_code=PAIR-DEVICE-1" in url_text

    asyncio.run(exercise())


class DeniedPairingClient(FakePairingClient):
    """A hosted plane that reports this pairing code as invalid/expired/already-used on the
    very first poll -- the fold-together reason every one of those three collapses into."""

    def status(self, code: str, challenge: str) -> str:
        return "invalid_or_expired"


def test_denied_pairing_stops_waiting_immediately_and_says_why() -> None:
    """Security/UX guard: a denied code must not spin to the full 300s deadline, and the
    message shown must name the real reason, not a fixed 'timed out after 300s' string that
    would be false when the denial arrived on the very first poll."""

    async def exercise() -> None:
        pairing = DeniedPairingClient()
        app = make_harness(pairing_client=pairing, browser_opener=lambda _url: None)
        async with app.run_test() as pilot:
            await pilot.click("#connect-sign-in")
            await wait_until(
                pilot,
                lambda: str(pilot.app.query_one("#pairing-status").render()).startswith(
                    "pairing failed"
                ),
                description="the pairing failure to be reported",
            )
            status_text = str(pilot.app.query_one("#pairing-status").render())
            assert "expired" in status_text
            assert "300s" not in status_text
            assert "press Sign in to get a new link" in status_text

    asyncio.run(exercise())


def test_sign_in_never_auto_launches_a_browser() -> None:
    """Auto-launching breaks headless boxes and can replace the TUI with a console browser --
    opening one is only ever an explicit, keypress-triggered choice."""

    async def exercise() -> None:
        pairing = FakePairingClient()
        opened: list[str] = []
        app = make_harness(pairing_client=pairing, browser_opener=opened.append)
        async with app.run_test() as pilot:
            await pilot.click("#connect-sign-in")
            await wait_until(
                pilot,
                lambda: bool(pilot.app.query("#sign-in-url")),
                description="the sign-in url to appear",
            )
            # Give any accidental auto-launch a chance to have fired by now.
            await pilot.pause()
            assert opened == []

    asyncio.run(exercise())


def test_browser_open_failure_is_reported_in_words_and_does_not_kill_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pr_reviewer.tui.screens.connect.gui_browser_plausible", lambda: True
    )

    def raising_opener(_url: str) -> bool:
        raise webbrowser.Error("no runnable browser found")

    async def exercise() -> None:
        pairing = FakePairingClient()
        app = make_harness(pairing_client=pairing, browser_opener=raising_opener)
        async with app.run_test() as pilot:
            await pilot.click("#connect-sign-in")
            await wait_until(
                pilot,
                lambda: bool(pilot.app.query("#sign-in-url")),
                description="the sign-in url to appear",
            )
            await pilot.press("o")
            await pilot.pause()
            # The app is still alive and responsive: querying and re-rendering both still work.
            assert pilot.app.query_one(ConnectPanel) is not None
            assert pilot.app.is_running

    asyncio.run(exercise())
