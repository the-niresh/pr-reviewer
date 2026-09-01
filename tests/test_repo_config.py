"""Per-repository reviewer configuration persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from pr_reviewer.local_store.repo_config import (
    RepoConfigStore,
    RepoModelChoice,
    default_repo_config_path,
    default_repo_model_choice,
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
