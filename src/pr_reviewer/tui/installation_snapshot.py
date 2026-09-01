"""Local installation snapshot for the TUI profile and repositories screens."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RepositoryPermission:
    github_repository_id: int
    name: str


@dataclass(frozen=True)
class InstallationSnapshot:
    github_login: str
    github_user_id: int
    installation_id: int
    repositories: tuple[RepositoryPermission, ...]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> InstallationSnapshot:
        repositories = tuple(
            RepositoryPermission(
                github_repository_id=int(item["github_repository_id"]),
                name=str(item["name"]),
            )
            for item in payload.get("repositories", [])
        )
        return cls(
            github_login=str(payload["github_login"]),
            github_user_id=int(payload["github_user_id"]),
            installation_id=int(payload["installation_id"]),
            repositories=repositories,
        )


def default_snapshot_path(config_dir: Path | None = None) -> Path:
    root = config_dir or (Path.home() / ".config" / "pr-reviewer")
    return root / "installation.json"


def load_installation_snapshot(path: Path) -> InstallationSnapshot | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("installation snapshot must be a JSON object")
    return InstallationSnapshot.from_mapping(payload)


def save_installation_snapshot(path: Path, snapshot: InstallationSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "github_login": snapshot.github_login,
        "github_user_id": snapshot.github_user_id,
        "installation_id": snapshot.installation_id,
        "repositories": [asdict(repo) for repo in snapshot.repositories],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
