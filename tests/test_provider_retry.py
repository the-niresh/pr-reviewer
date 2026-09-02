"""Retry policy has hard limits and only retries an explicit rate limit."""

from __future__ import annotations

from pr_reviewer.models.provider_errors import ProviderErrorKind


def _failure(kind: ProviderErrorKind, retry_after_seconds: float | None = None) -> object:
    from pr_reviewer.models.provider_errors import ProviderFailure

    return ProviderFailure(
        provider="openai",
        kind=kind,
        reason="provider response",
        retry_after_seconds=retry_after_seconds,
    )


def test_out_of_tokens_is_not_retried_even_once() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind
    from pr_reviewer.models.retry import RetryPolicy, retry_provider_call

    attempts = 0

    def attempt() -> object:
        nonlocal attempts
        attempts += 1
        return _failure(ProviderErrorKind.OUT_OF_TOKENS)

    result = retry_provider_call(
        attempt,
        policy=RetryPolicy(max_attempts=3, max_elapsed_seconds=10),
    )

    assert attempts == 1
    assert result.failure is not None
    assert result.failure.kind is ProviderErrorKind.OUT_OF_TOKENS


def test_retry_after_takes_priority_over_backoff() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind
    from pr_reviewer.models.retry import RetryPolicy, retry_provider_call

    delays: list[float] = []
    attempts = 0

    def attempt() -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _failure(ProviderErrorKind.RETRYABLE_RATE_LIMIT, retry_after_seconds=7)
        return "complete"

    result = retry_provider_call(
        attempt,
        policy=RetryPolicy(max_attempts=3, max_elapsed_seconds=10),
        sleep=delays.append,
    )

    assert result.value == "complete"
    assert delays == [7]


def test_attempt_cap_ends_repeated_rate_limits() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind
    from pr_reviewer.models.retry import RetryPolicy, retry_provider_call

    attempts = 0

    def attempt() -> object:
        nonlocal attempts
        attempts += 1
        return _failure(ProviderErrorKind.RETRYABLE_RATE_LIMIT)

    result = retry_provider_call(
        attempt,
        policy=RetryPolicy(max_attempts=2, max_elapsed_seconds=10),
    )

    assert attempts == 2
    assert result.failure is not None


def test_wall_clock_cap_stops_before_another_attempt() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind
    from pr_reviewer.models.retry import RetryPolicy, retry_provider_call

    attempts = 0
    now = iter([0.0, 0.0, 2.0])

    def attempt() -> object:
        nonlocal attempts
        attempts += 1
        return _failure(ProviderErrorKind.RETRYABLE_RATE_LIMIT)

    result = retry_provider_call(
        attempt,
        policy=RetryPolicy(max_attempts=3, max_elapsed_seconds=1),
        clock=lambda: next(now),
        sleep=lambda _: None,
    )

    assert attempts == 1
    assert result.failure is not None
