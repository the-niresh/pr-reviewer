"""Classify provider failures before choosing whether a call may be retried."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from pr_reviewer.models.providers import ProviderName


class ProviderErrorKind(StrEnum):
    RETRYABLE_RATE_LIMIT = "retryable_rate_limit"
    OUT_OF_TOKENS = "out_of_tokens"
    BAD_KEY = "bad_key"
    PROVIDER_OVERLOADED = "provider_overloaded"
    BAD_REQUEST = "bad_request"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderFailure:
    """A classified provider response, kept separate from retry policy."""

    provider: ProviderName
    kind: ProviderErrorKind
    reason: str
    retry_after_seconds: float | None = None


def _error_message(body: object) -> str:
    if not isinstance(body, Mapping):
        return ""
    error = body.get("error")
    if not isinstance(error, Mapping):
        return ""
    return " ".join(
        str(error.get(field, "")) for field in ("code", "type", "message")
    ).lower()


def classify_provider_failure(
    *,
    provider: ProviderName | str,
    status_code: int,
    headers: Mapping[str, str],
    body: object,
) -> ProviderErrorKind:
    """Map known provider responses into the complete local error vocabulary."""
    if status_code == 401:
        return ProviderErrorKind.BAD_KEY
    if status_code == 400:
        return ProviderErrorKind.BAD_REQUEST
    if status_code in {503, 529}:
        return ProviderErrorKind.PROVIDER_OVERLOADED
    if provider == "anthropic":
        if status_code == 402:
            return ProviderErrorKind.OUT_OF_TOKENS
        if status_code == 429:
            return (
                ProviderErrorKind.RETRYABLE_RATE_LIMIT
                if any(key.lower() == "retry-after" for key in headers)
                else ProviderErrorKind.OUT_OF_TOKENS
            )
    if provider == "openai" and status_code == 429:
        message = _error_message(body)
        if any(
            marker in message
            for marker in ("credit balance", "spend limit", "usage limit", "quota")
        ):
            return ProviderErrorKind.OUT_OF_TOKENS
        if "rate limit" in message:
            return ProviderErrorKind.RETRYABLE_RATE_LIMIT
    return ProviderErrorKind.UNKNOWN


def is_retryable(kind: ProviderErrorKind) -> bool:
    """Only an explicit rate limit may enter the retry loop."""
    return kind is ProviderErrorKind.RETRYABLE_RATE_LIMIT
