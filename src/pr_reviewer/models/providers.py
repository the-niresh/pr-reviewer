"""Authentication details for the providers supported by the local runner."""

from __future__ import annotations

from typing import Literal

ProviderName = Literal["openai", "anthropic"]

ANTHROPIC_VERSION = "2023-06-01"


def provider_auth_headers(provider: ProviderName, api_key: str) -> dict[str, str]:
    """Return only the headers accepted by one provider's API."""
    if provider == "openai":
        return {"authorization": f"Bearer {api_key}"}
    return {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
