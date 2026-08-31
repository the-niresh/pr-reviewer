"""Capped exponential retry with jitter, Retry-After, and a hard deadline.

Sleep is injected. If the next wait would pass the deadline, this raises
RetryDeadlineExceeded instead of polling.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping


class RetryDeadlineExceeded(RuntimeError):
    """The next retry wait would pass the hard deadline."""


def retry_after_seconds(headers: Mapping[str, str] | None) -> float | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def next_backoff(
    attempt: int,
    *,
    base_seconds: float = 0.5,
    cap_seconds: float = 30.0,
    retry_after: float | None = None,
    rng: Callable[[], float] | None = None,
    jitter: float = 0.1,
) -> float:
    if retry_after is not None:
        return min(max(0.0, retry_after), cap_seconds)
    delay = min(cap_seconds, base_seconds * (2**attempt))
    sample = rng() if rng is not None else random.random()
    return float(delay * (1.0 - jitter + (2 * jitter * sample)))


def is_neon_interruption(error: BaseException) -> bool:
    if type(error).__name__ == "OperationalError":
        return True
    message = str(error).lower()
    return "server closed the connection" in message or "connection unexpectedly" in message


def run_with_retry[T](
    operation: Callable[[], T],
    *,
    is_retryable: Callable[[BaseException], bool],
    deadline_monotonic: float,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    max_attempts: int = 5,
    base_seconds: float = 0.5,
    cap_seconds: float = 30.0,
    rng: Callable[[], float] | None = None,
    retry_after: Callable[[BaseException], float | None] | None = None,
) -> T:
    last_error: BaseException | None = None
    for attempt in range(max_attempts):
        if clock() >= deadline_monotonic:
            raise RetryDeadlineExceeded(
                f"retry missed its deadline after {attempt} attempt(s)"
            )
        try:
            return operation()
        except BaseException as error:
            last_error = error
            if not is_retryable(error) or attempt + 1 >= max_attempts:
                raise
            extra = None if retry_after is None else retry_after(error)
            delay = next_backoff(
                attempt,
                base_seconds=base_seconds,
                cap_seconds=cap_seconds,
                retry_after=extra,
                rng=rng,
            )
            remaining = deadline_monotonic - clock()
            if delay > remaining:
                raise RetryDeadlineExceeded(
                    f"retry sleep {delay:.3f}s would miss its deadline "
                    f"({remaining:.3f}s remaining)"
                ) from error
            sleep(delay)
    assert last_error is not None
    raise last_error
