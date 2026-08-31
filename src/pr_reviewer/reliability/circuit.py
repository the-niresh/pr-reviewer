"""Durable connector circuit policy. Unknown is open. Missing is closed.

A circuit whose state cannot be read is neither obviously open nor closed.
This module chooses OPEN (deny new calls). Justification: the same fail-closed
default as unset budgets and Task 15 confidentiality. If we cannot read circuit
state, we also cannot record the next failure; allowing traffic would hammer a
connector that may already be dead. A missing row is different: the connector
has never opened, so the first call is allowed.

Half-open probing compares `now` to `probe_after_monotonic`. There is no poll loop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

CircuitStateName = Literal["closed", "open", "half_open"]
UNKNOWN_CIRCUIT_STATE: CircuitStateName = "open"


class CircuitStateUnreadable(RuntimeError):
    """The durable circuit row could not be read."""


class CircuitOpen(RuntimeError):
    """The circuit is open and no probe is due."""


@dataclass(frozen=True)
class CircuitSnapshot:
    connector: str
    state: CircuitStateName
    consecutive_failures: int
    probe_after_monotonic: float | None


def decide_unreadable_circuit() -> CircuitStateName:
    return UNKNOWN_CIRCUIT_STATE


def load_or_unknown(
    connector: str,
    *,
    load: Callable[[], CircuitSnapshot | None],
) -> CircuitSnapshot | None:
    try:
        return load()
    except CircuitStateUnreadable:
        return CircuitSnapshot(
            connector=connector,
            state=UNKNOWN_CIRCUIT_STATE,
            consecutive_failures=0,
            probe_after_monotonic=None,
        )


def allow_call(snapshot: CircuitSnapshot | None, *, now: float) -> bool:
    if snapshot is None or snapshot.state == "closed":
        return True
    if snapshot.state == "half_open":
        return True
    if snapshot.probe_after_monotonic is None:
        return False
    return now >= snapshot.probe_after_monotonic


def seconds_until_probe(snapshot: CircuitSnapshot, *, now: float) -> float:
    if snapshot.probe_after_monotonic is None:
        return 0.0
    return max(0.0, snapshot.probe_after_monotonic - now)
