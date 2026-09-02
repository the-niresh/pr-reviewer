"""Provider requests use only the authentication scheme each API accepts."""

from typing import Literal

import pytest


@pytest.mark.parametrize(
    ("provider", "api_key", "expected", "forbidden"),
    [
        (
            "openai",
            "openai-key",
            {"authorization": "Bearer openai-key"},
            {"x-api-key", "anthropic-version"},
        ),
        (
            "anthropic",
            "anthropic-key",
            {"x-api-key": "anthropic-key", "anthropic-version": "2023-06-01"},
            {"authorization"},
        ),
    ],
)
def test_provider_auth_headers_are_not_interchangeable(
    provider: Literal["openai", "anthropic"],
    api_key: str,
    expected: dict[str, str],
    forbidden: set[str],
) -> None:
    from pr_reviewer.models.providers import provider_auth_headers

    headers = provider_auth_headers(provider, api_key)

    assert headers == expected
    assert forbidden.isdisjoint(headers)
