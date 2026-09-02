"""Bounded retry policy for provider calls."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from pr_reviewer.models.provider_errors import ProviderFailure, is_retryable


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    max_elapsed_seconds: float
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.max_elapsed_seconds <= 0:
            raise ValueError("max_elapsed_seconds must be positive")
        if self.initial_delay_seconds <= 0 or self.max_delay_seconds <= 0:
            raise ValueError("retry delays must be positive")


@dataclass(frozen=True)
class RetryResult[Result]:
    value: Result | None = None
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.failure is None):
            raise ValueError("retry result must contain exactly one outcome")


def retry_provider_call[Result](
    attempt: Callable[[], Result | ProviderFailure],
    *,
    policy: RetryPolicy,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> RetryResult[Result]:
    """Retry only classified rate limits without exceeding either hard limit."""
    started = clock()
    last_failure: ProviderFailure | None = None
    for attempt_number in range(1, policy.max_attempts + 1):
        if attempt_number > 1 and clock() - started >= policy.max_elapsed_seconds:
            assert last_failure is not None
            return RetryResult(failure=last_failure)
        outcome = attempt()
        if not isinstance(outcome, ProviderFailure):
            return RetryResult(value=outcome)
        last_failure = outcome
        if not is_retryable(outcome.kind) or attempt_number == policy.max_attempts:
            return RetryResult(failure=outcome)
        elapsed = clock() - started
        remaining = policy.max_elapsed_seconds - elapsed
        delay = _retry_delay(outcome, attempt_number, policy)
        if remaining <= 0 or delay > remaining:
            return RetryResult(failure=outcome)
        sleep(delay)
    raise AssertionError("attempt cap must return before reaching this point")


def _retry_delay(failure: ProviderFailure, attempt_number: int, policy: RetryPolicy) -> float:
    if failure.retry_after_seconds is not None:
        return failure.retry_after_seconds
    return float(
        min(policy.initial_delay_seconds * (2 ** (attempt_number - 1)), policy.max_delay_seconds)
    )
