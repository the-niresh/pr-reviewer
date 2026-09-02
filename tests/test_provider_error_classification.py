"""Provider failures are classified before retry policy sees them."""

from __future__ import annotations

import pytest

from pr_reviewer.models.provider_errors import ProviderErrorKind


def _classify(
    provider: str,
    status_code: int,
    *,
    message: str = "",
    headers: dict[str, str] | None = None,
) -> ProviderErrorKind:
    from pr_reviewer.models.provider_errors import classify_provider_failure

    return classify_provider_failure(
        provider=provider,
        status_code=status_code,
        headers=headers or {},
        body={"error": {"message": message}},
    )


def test_openai_rate_limit_is_retryable() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind

    assert (
        _classify("openai", 429, message="Rate limit reached")
        == ProviderErrorKind.RETRYABLE_RATE_LIMIT
    )


@pytest.mark.parametrize(
    "message",
    ["credit balance exhausted", "project spend limit", "usage limit reached"],
)
def test_openai_credit_or_limit_is_out_of_tokens(message: str) -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind

    assert _classify("openai", 429, message=message) == ProviderErrorKind.OUT_OF_TOKENS


def test_anthropic_429_with_retry_after_is_retryable() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind

    assert (
        _classify("anthropic", 429, headers={"retry-after": "12"})
        == ProviderErrorKind.RETRYABLE_RATE_LIMIT
    )


def test_anthropic_429_without_retry_after_is_out_of_tokens() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind

    assert _classify("anthropic", 429) == ProviderErrorKind.OUT_OF_TOKENS


def test_anthropic_402_is_out_of_tokens() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind

    assert _classify("anthropic", 402) == ProviderErrorKind.OUT_OF_TOKENS


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_401_is_a_bad_key_not_out_of_tokens(provider: str) -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind

    assert _classify(provider, 401) == ProviderErrorKind.BAD_KEY


def test_unrecognised_failure_is_unknown_and_not_retryable() -> None:
    from pr_reviewer.models.provider_errors import ProviderErrorKind, is_retryable

    failure = _classify("openai", 418, message="teapot")

    assert failure == ProviderErrorKind.UNKNOWN
    assert is_retryable(failure) is False
