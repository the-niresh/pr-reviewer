"""Per-repository reviewer configuration persisted on the runner machine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pr_reviewer.security.instruction_sources import ReviewPolicy, default_review_policy


class RepoConfigStore:
    """JSON-backed store for per-repository ReviewPolicy values."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def get(self, github_repository_id: int) -> ReviewPolicy:
        payload = self._read_payload()
        repositories = payload.get("repositories", {})
        key = str(github_repository_id)
        if key not in repositories:
            return default_review_policy()
        return ReviewPolicy.model_validate(repositories[key])

    def set(self, github_repository_id: int, policy: ReviewPolicy) -> None:
        payload = self._read_payload()
        repositories = payload.setdefault("repositories", {})
        repositories[str(github_repository_id)] = policy.model_dump()
        self._write_payload(payload)

    def all_for(self, github_repository_ids: list[int]) -> dict[int, ReviewPolicy]:
        return {repo_id: self.get(repo_id) for repo_id in github_repository_ids}

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


def default_repo_config_path(config_dir: Path | None = None) -> Path:
    root = config_dir or (Path.home() / ".config" / "pr-reviewer")
    return root / "repo_config.json"
