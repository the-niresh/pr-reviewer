"""Per-repository reviewer configuration persisted on the runner machine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pr_reviewer.models.catalogue import (
    default_model_for,
    is_known_provider_model,
    list_providers,
)
from pr_reviewer.security.instruction_sources import ReviewPolicy, default_review_policy

_MODEL_CHOICE_KEYS = ("provider_id", "model_id")


@dataclass(frozen=True)
class RepoModelChoice:
    provider_id: str
    model_id: str


def default_repo_model_choice() -> RepoModelChoice:
    first = list_providers()[0]
    return RepoModelChoice(
        provider_id=first.provider_id,
        model_id=default_model_for(first.provider_id),
    )


def validate_repo_model_choice(choice: RepoModelChoice) -> RepoModelChoice:
    if not is_known_provider_model(choice.provider_id, choice.model_id):
        raise ValueError(
            f"unknown provider/model pair: {choice.provider_id}/{choice.model_id}"
        )
    return choice


class RepoConfigStore:
    """JSON-backed store for per-repository ReviewPolicy and model choice values."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def get(self, github_repository_id: int) -> ReviewPolicy:
        entry = self._repo_entry(github_repository_id)
        policy_data, _choice_data = _split_repo_entry(entry)
        if not policy_data:
            return default_review_policy()
        return ReviewPolicy.model_validate(policy_data)

    def get_model_choice(self, github_repository_id: int) -> RepoModelChoice:
        entry = self._repo_entry(github_repository_id)
        _policy_data, choice_data = _split_repo_entry(entry)
        if "provider_id" in choice_data and "model_id" in choice_data:
            return validate_repo_model_choice(
                RepoModelChoice(
                    provider_id=str(choice_data["provider_id"]),
                    model_id=str(choice_data["model_id"]),
                )
            )
        return default_repo_model_choice()

    def set(self, github_repository_id: int, policy: ReviewPolicy) -> None:
        payload = self._read_payload()
        repositories = payload.setdefault("repositories", {})
        key = str(github_repository_id)
        entry = dict(repositories.get(key, {}))
        _policy_data, choice_data = _split_repo_entry(entry)
        repositories[key] = {**policy.model_dump(), **choice_data}
        self._write_payload(payload)

    def set_model_choice(self, github_repository_id: int, choice: RepoModelChoice) -> None:
        validated = validate_repo_model_choice(choice)
        payload = self._read_payload()
        repositories = payload.setdefault("repositories", {})
        key = str(github_repository_id)
        entry = dict(repositories.get(key, {}))
        policy_data, _choice_data = _split_repo_entry(entry)
        if not policy_data:
            policy_data = default_review_policy().model_dump()
        repositories[key] = {
            **policy_data,
            "provider_id": validated.provider_id,
            "model_id": validated.model_id,
        }
        self._write_payload(payload)

    def all_for(self, github_repository_ids: list[int]) -> dict[int, ReviewPolicy]:
        return {repo_id: self.get(repo_id) for repo_id in github_repository_ids}

    def all_model_choices_for(
        self, github_repository_ids: list[int]
    ) -> dict[int, RepoModelChoice]:
        return {repo_id: self.get_model_choice(repo_id) for repo_id in github_repository_ids}

    def _repo_entry(self, github_repository_id: int) -> dict[str, Any]:
        payload = self._read_payload()
        repositories = payload.get("repositories", {})
        raw = repositories.get(str(github_repository_id), {})
        if not isinstance(raw, dict):
            raise ValueError("repository config must be a JSON object")
        return dict(raw)

    def _read_payload(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"repositories": {}}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("repo config must be a JSON object")
        return raw

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _split_repo_entry(entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    policy_data = {key: value for key, value in entry.items() if key not in _MODEL_CHOICE_KEYS}
    choice_data = {key: entry[key] for key in _MODEL_CHOICE_KEYS if key in entry}
    return policy_data, choice_data


def default_repo_config_path(config_dir: Path | None = None) -> Path:
    root = config_dir or (Path.home() / ".config" / "pr-reviewer")
    return root / "repo_config.json"
