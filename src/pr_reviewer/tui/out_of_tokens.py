"""Terminal copy when a provider balance is exhausted.

Reuses the classified terminal state from models/provider_errors.py rather than inventing a
second OutOfTokensState: that module is what actually decides a provider is out of tokens
(classify_provider_failure), so its state is the one true source for "which provider, why".
"""

from __future__ import annotations

from pr_reviewer.models.catalogue import list_providers
from pr_reviewer.models.provider_errors import OutOfTokensState
from pr_reviewer.models.providers import ProviderName

__all__ = ["OutOfTokensState", "out_of_tokens_message"]


def _provider_label(provider: ProviderName) -> str:
    for entry in list_providers():
        if entry.provider_id == provider:
            return entry.label
    return provider


def out_of_tokens_message(provider: ProviderName) -> str:
    """Plain words naming the provider and the one thing to do about it.

    Deliberately never renders OutOfTokensState.reason: that field carries the raw provider
    payload, which can contain JSON fragments or a traceback-shaped string -- exactly what
    must never reach the screen.
    """
    return (
        f"{_provider_label(provider)} balance is exhausted. "
        "Add credits or switch provider to continue reviewing."
    )
