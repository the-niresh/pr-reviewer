"""Well-known model providers and their allowed models for BYOK."""

from __future__ import annotations

from dataclasses import dataclass

MAX_MODELS_PER_PROVIDER = 5


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    label: str


@dataclass(frozen=True)
class ProviderEntry:
    provider_id: str
    label: str
    models: tuple[ModelEntry, ...]


def _build_catalogue() -> tuple[ProviderEntry, ...]:
    providers = (
        ProviderEntry(
            provider_id="openai",
            label="OpenAI",
            models=(
                ModelEntry("gpt-4o-mini", "GPT-4o mini"),
                ModelEntry("gpt-4o", "GPT-4o"),
                ModelEntry("gpt-4.1-mini", "GPT-4.1 mini"),
                ModelEntry("gpt-4.1", "GPT-4.1"),
                ModelEntry("o3-mini", "o3 mini"),
            ),
        ),
        ProviderEntry(
            provider_id="anthropic",
            label="Anthropic",
            models=(
                ModelEntry("claude-3-5-haiku-latest", "Claude 3.5 Haiku"),
                ModelEntry("claude-3-5-sonnet-latest", "Claude 3.5 Sonnet"),
                ModelEntry("claude-3-7-sonnet-latest", "Claude 3.7 Sonnet"),
                ModelEntry("claude-sonnet-4-20250514", "Claude Sonnet 4"),
                ModelEntry("claude-haiku-4-20250414", "Claude Haiku 4"),
            ),
        ),
    )
    for provider in providers:
        if len(provider.models) > MAX_MODELS_PER_PROVIDER:
            raise ValueError(
                f"{provider.provider_id} lists more than {MAX_MODELS_PER_PROVIDER} models"
            )
    return providers


CATALOGUE: tuple[ProviderEntry, ...] = _build_catalogue()


def list_providers() -> tuple[ProviderEntry, ...]:
    return CATALOGUE


def models_for(provider_id: str) -> tuple[ModelEntry, ...]:
    for provider in CATALOGUE:
        if provider.provider_id == provider_id:
            return provider.models
    raise KeyError(f"unknown provider: {provider_id}")


def is_known_provider_model(provider_id: str, model_id: str) -> bool:
    try:
        return any(entry.model_id == model_id for entry in models_for(provider_id))
    except KeyError:
        return False


def default_model_for(provider_id: str) -> str:
    models = models_for(provider_id)
    return models[0].model_id
