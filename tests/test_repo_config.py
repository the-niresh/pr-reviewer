"""Per-repository reviewer configuration persistence."""

from __future__ import annotations

from pathlib import Path

from pr_reviewer.local_store.repo_config import RepoConfigStore, default_repo_config_path
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
