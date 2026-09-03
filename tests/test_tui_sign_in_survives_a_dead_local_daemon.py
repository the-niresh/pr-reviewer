"""Sign-in must not die when the local runner daemon is not running.

The connect screen polled http://127.0.0.1:8742 for pairing status. A new user has not
started that daemon yet, so httpx raised ConnectError out of the sign-in worker and Textual
tore the app down moments after the link appeared on screen. Two things are asserted here:
with no status client injected the poll goes to the hosted pairing client, which already
satisfies the same protocol and owns the pairing state; and any failure while waiting is
reported in words rather than killing the TUI.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from textual.app import App, ComposeResult
from textual.pilot import Pilot

from pr_reviewer.tui.screens.connect import ConnectConfig, ConnectPanel


async def wait_until(
    pilot: Pilot[Any], condition: Callable[[], bool], *, description: str, timeout: float = 3.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await pilot.pause()
    raise AssertionError(f"timed out after {timeout}s waiting for {description}")


class HostedClient:
    """Stands in for HostedPairingClient, which satisfies the status protocol too."""

    def __init__(self) -> None:
        self.status_calls = 0

    def create_code(self, device_name: str, challenge: str) -> str:
        del device_name, challenge
        return "PAIR-DEVICE-1"

    def status(self, code: str, challenge: str) -> str:
        del code, challenge
        self.status_calls += 1
        return "exchangeable"

    def exchange(self, code: str, proof: str) -> str:
        del code, proof
        return "runner-credential"


class RefusingClient(HostedClient):
    def status(self, code: str, challenge: str) -> str:
        del code, challenge
        raise ConnectionRefusedError("[Errno 111] Connection refused")


def make_harness(pairing_client: HostedClient) -> App[None]:
    class Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield ConnectPanel(
                config=ConnectConfig(
                    hosted_origin="https://reviewer.niresh.tech",
                    device_name="test-laptop",
                ),
                pairing_client=pairing_client,
                browser_opener=lambda _url: None,
                pairing_poll_interval=0.0,
            )

    return Harness()


def _run(pairing_client: HostedClient) -> tuple[bool, str]:
    async def exercise() -> tuple[bool, str]:
        app = make_harness(pairing_client)
        async with app.run_test() as pilot:
            await pilot.click("#connect-sign-in")
            panel = pilot.app.query_one(ConnectPanel)
            await wait_until(
                pilot,
                lambda: panel.pairing_status not in {"not started", "creating a sign-in link..."},
                description="the wait to resolve",
            )
            return pilot.app.is_running, panel.pairing_status

    return asyncio.run(exercise())


def test_the_poll_goes_to_the_hosted_client_not_the_local_daemon() -> None:
    client = HostedClient()
    running, status = _run(client)
    assert running, "the app must still be alive after signing in"
    assert client.status_calls > 0, "pairing status must be polled on the hosted client"
    assert status == "signed in", status


def test_a_refused_poll_is_reported_instead_of_killing_the_app() -> None:
    running, status = _run(RefusingClient())
    assert running, "a refused pairing poll must never tear the TUI down"
    assert status.startswith("pairing failed"), status
    assert "Connection refused" in status, status
