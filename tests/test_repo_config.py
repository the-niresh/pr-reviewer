"""Per-repository reviewer configuration persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from pr_reviewer.local_store.repo_config import (
    RepoConfigStore,
    RepoModelChoice,
    RepositoryPromptVersion,
    default_repo_config_path,
    default_repo_model_choice,
    repository_prompt_name,
    validate_repo_model_choice,
)
from pr_reviewer.security.instruction_sources import ReviewPolicy, default_review_policy


def test_missing_repository_returns_default_policy(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    policy = store.get(11)
    assert policy == default_review_policy()
    assert policy.auto_post is False
    assert policy.instructions_enabled is False


def test_set_and_get_persist_per_repository_policy(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    custom = ReviewPolicy(instructions_enabled=True, auto_post=False, specialist_mode=True)
    store.set(11, custom)
    store.set(12, ReviewPolicy(auto_post=True))

    assert store.get(11) == custom
    assert store.get(12).auto_post is True
    assert store.get(99) == default_review_policy()


def test_repo_config_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "repo_config.json"
    first = RepoConfigStore(path)
    first.set(42, ReviewPolicy(instructions_enabled=True, budget_tokens=64_000))

    second = RepoConfigStore(path)
    loaded = second.get(42)
    assert loaded.instructions_enabled is True
    assert loaded.budget_tokens == 64_000


def test_all_for_returns_only_requested_repository_ids(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    store.set(11, ReviewPolicy(specialist_mode=True))
    store.set(12, ReviewPolicy(auto_post=True))

    policies = store.all_for([11, 12, 13])
    assert policies[11].specialist_mode is True
    assert policies[12].auto_post is True
    assert policies[13] == default_review_policy()


def test_default_repo_config_path_uses_config_dir() -> None:
    assert default_repo_config_path(Path("/tmp/example")).name == "repo_config.json"


def test_missing_repository_returns_default_model_choice(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    choice = store.get_model_choice(11)
    assert choice == default_repo_model_choice()


def test_set_and_get_persist_per_repository_model_choice(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    choice = RepoModelChoice(provider_id="anthropic", model_id="claude-3-5-haiku-latest")
    store.set_model_choice(11, choice)

    assert store.get_model_choice(11) == choice
    assert store.get_model_choice(12) == default_repo_model_choice()


def test_model_choice_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "repo_config.json"
    first = RepoConfigStore(path)
    first.set_model_choice(
        42,
        RepoModelChoice(provider_id="openai", model_id="gpt-4o"),
    )

    second = RepoConfigStore(path)
    assert second.get_model_choice(42) == RepoModelChoice(
        provider_id="openai",
        model_id="gpt-4o",
    )


def test_setting_policy_preserves_model_choice(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    choice = RepoModelChoice(provider_id="openai", model_id="gpt-4o-mini")
    store.set_model_choice(11, choice)
    store.set(11, ReviewPolicy(instructions_enabled=True))

    assert store.get(11).instructions_enabled is True
    assert store.get_model_choice(11) == choice


def test_setting_model_choice_preserves_policy(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    store.set(11, ReviewPolicy(specialist_mode=True))
    store.set_model_choice(
        11,
        RepoModelChoice(provider_id="anthropic", model_id="claude-3-5-sonnet-latest"),
    )

    assert store.get(11).specialist_mode is True
    assert store.get_model_choice(11).provider_id == "anthropic"


def test_validate_repo_model_choice_rejects_unknown_pairs() -> None:
    with pytest.raises(ValueError):
        validate_repo_model_choice(
            RepoModelChoice(provider_id="openai", model_id="not-a-real-model")
        )


def test_add_repository_prompt_creates_versioned_entries(tmp_path: Path) -> None:
    store = RepoConfigStore(tmp_path / "repo_config.json")
    first = store.add_repository_prompt(11, "Focus on API migrations")
    second = store.add_repository_prompt(11, "Also check auth boundaries")

    assert first == RepositoryPromptVersion(
        version="1", content="Focus on API migrations", locked=False
    )
    assert second.version == "2"
    assert store.get_active_repository_prompt(11) == second
    assert len(store.list_repository_prompt_versions(11)) == 2


def test_locked_repository_prompt_cannot_be_re_registered(tmp_path: Path) -> None:
    from pr_reviewer.prompts.registry import PromptVersionImmutable

    store = RepoConfigStore(tmp_path / "repo_config.json")
    store.add_repository_prompt(11, "Focus on API migrations")
    store.mark_repository_prompt_used(11, "1")

    versions = store.list_repository_prompt_versions(11)
    assert versions[0].locked is True

    registry = store._prompt_registry_for(11, {"1": {"content": "mutated", "locked": True}})
    name = repository_prompt_name(11)
    with pytest.raises(PromptVersionImmutable):
        registry.register(name, "1", "mutated")


def test_repository_prompt_versions_survive_reload(tmp_path: Path) -> None:
    path = tmp_path / "repo_config.json"
    first = RepoConfigStore(path)
    first.add_repository_prompt(42, "Watch database migrations")

    second = RepoConfigStore(path)
    active = second.get_active_repository_prompt(42)
    assert active is not None
    assert active.content == "Watch database migrations"
    assert active.version == "1"
