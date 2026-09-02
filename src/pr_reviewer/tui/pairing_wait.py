"""Bounded wait for pairing completion via the local daemon."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from pr_reviewer.tui.pairing_client import PairingStatus

DEFAULT_LOCAL_DAEMON_ORIGIN = "http://127.0.0.1:8742"


class PairingWaitDeadlineExceeded(RuntimeError):
    """Pairing did not complete before the hard deadline."""


class LocalPairingStatusClient(Protocol):
    def status(self, code: str, challenge: str) -> PairingStatus: ...


class HttpLocalPairingStatusClient:
    def __init__(self, local_origin: str = DEFAULT_LOCAL_DAEMON_ORIGIN) -> None:
        self._local_origin = local_origin.rstrip("/")

    def status(self, code: str, challenge: str) -> PairingStatus:
        import httpx

        response = httpx.get(
            f"{self._local_origin}/onboarding/pairing/status",
            params={"code": code, "challenge": challenge},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        raw_state = payload.get("state")
        if raw_state == "pending":
            return "pending"
        if raw_state == "exchangeable":
            return "exchangeable"
        return "invalid_or_expired"


def wait_for_pairing(
    *,
    code: str,
    challenge: str,
    status_client: LocalPairingStatusClient,
    deadline_seconds: float = 300.0,
    poll_interval_seconds: float = 2.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    deadline = clock() + deadline_seconds
    while clock() < deadline:
        state = status_client.status(code, challenge)
        if state == "exchangeable":
            return
        if state == "invalid_or_expired":
            raise PairingWaitDeadlineExceeded("pairing code expired")
        sleep(poll_interval_seconds)
    raise PairingWaitDeadlineExceeded(
        f"pairing did not complete within {deadline_seconds}s"
    )
