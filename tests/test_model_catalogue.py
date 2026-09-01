"""Provider and model catalogue for BYOK."""

from __future__ import annotations

import pytest

from pr_reviewer.models.catalogue import (
    CATALOGUE,
    MAX_MODELS_PER_PROVIDER,
    default_model_for,
    is_known_provider_model,
    list_providers,
    models_for,
)


def test_catalogue_lists_only_well_known_providers() -> None:
    provider_ids = {provider.provider_id for provider in CATALOGUE}
    assert provider_ids == {"openai", "anthropic"}


def test_each_provider_lists_at_most_five_models() -> None:
    for provider in list_providers():
        assert len(provider.models) <= MAX_MODELS_PER_PROVIDER


def test_models_for_returns_provider_models() -> None:
    openai_models = {entry.model_id for entry in models_for("openai")}
    assert "gpt-4o-mini" in openai_models
    anthropic_models = {entry.model_id for entry in models_for("anthropic")}
    assert "claude-3-5-haiku-latest" in anthropic_models


def test_unknown_provider_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown provider"):
        models_for("ollama")


def test_is_known_provider_model() -> None:
    assert is_known_provider_model("openai", "gpt-4o-mini") is True
    assert is_known_provider_model("openai", "not-a-model") is False
    assert is_known_provider_model("unknown", "gpt-4o-mini") is False


def test_default_model_is_the_first_listed_model() -> None:
    assert default_model_for("openai") == "gpt-4o-mini"
    assert default_model_for("anthropic") == "claude-3-5-haiku-latest"
