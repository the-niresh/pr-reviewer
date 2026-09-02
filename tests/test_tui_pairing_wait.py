"""Bounded wait for local daemon pairing status."""

from __future__ import annotations

import pytest

from pr_reviewer.tui.pairing_wait import (
    PairingWaitDeadlineExceeded,
    wait_for_pairing,
)


class SequenceStatusClient:
    def __init__(self, states: list[str]) -> None:
        self._states = list(states)
        self.calls: list[tuple[str, str]] = []

    def status(self, code: str, challenge: str) -> str:
        self.calls.append((code, challenge))
        if not self._states:
            return "pending"
        return self._states.pop(0)


def test_wait_for_pairing_returns_when_exchangeable() -> None:
    client = SequenceStatusClient(["pending", "exchangeable"])
    wait_for_pairing(
        code="PAIR-1",
        challenge="abc",
        status_client=client,
        poll_interval_seconds=0.0,
        deadline_seconds=5.0,
        sleep=lambda _seconds: None,
    )
    assert client.calls


def test_wait_for_pairing_raises_on_deadline() -> None:
    client = SequenceStatusClient(["pending", "pending", "pending"])
    with pytest.raises(PairingWaitDeadlineExceeded):
        wait_for_pairing(
            code="PAIR-1",
            challenge="abc",
            status_client=client,
            poll_interval_seconds=0.0,
            deadline_seconds=0.0,
            sleep=lambda _seconds: None,
        )
