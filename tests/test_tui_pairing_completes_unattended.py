"""Pairing completes without a keypress and the TUI advances."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.pilot import Pilot

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
        self._status = "pending"

    def create_code(self, device_name: str, challenge: str) -> str:
        return "PAIR-AUTO-1"

    def status(self, code: str, challenge: str) -> str:
        return self._status

    def set_exchangeable(self) -> None:
        self._status = "exchangeable"

    def exchange(self, code: str, proof: str) -> str:
        return "runner-credential-from-pairing"


class FakeLocalStatusClient:
    def __init__(self, pairing: FakePairingClient) -> None:
        self._pairing = pairing

    def status(self, code: str, challenge: str) -> str:
        return self._pairing.status(code, challenge)


def test_pairing_completes_unattended(tmp_path: Path) -> None:
    async def exercise() -> None:
        from pr_reviewer.tui.app import ReviewerApp

        pairing = FakePairingClient()
        secrets = __import__(
            "pr_reviewer.runner.secrets", fromlist=["FileSecretStore"]
        ).FileSecretStore(tmp_path)

        app = ReviewerApp(
            secrets=secrets,
            pairing_client=pairing,
            local_pairing_status_client=FakeLocalStatusClient(pairing),
            pairing_poll_interval=0.01,
            browser_opener=lambda _url: None,
        )
        async with app.run_test() as pilot:
            await pilot.click("#connect-sign-in")
            pairing.set_exchangeable()
            await wait_until(
                pilot,
                lambda: app.github_connected,
                description="github connection after pairing",
            )
            assert app.query_one("#model-access-screen") is not None

    asyncio.run(exercise())
