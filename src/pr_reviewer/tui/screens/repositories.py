"""Repositories screen listing installation-permitted repositories."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from pr_reviewer.local_store.repo_config import RepoConfigStore
from pr_reviewer.security.instruction_sources import ReviewPolicy, default_review_policy
from pr_reviewer.tui.installation_snapshot import InstallationSnapshot


def format_policy_summary(policy: ReviewPolicy) -> str:
    flags: list[str] = []
    if policy.instructions_enabled:
        flags.append("instructions")
    if policy.auto_post:
        flags.append("auto_post")
    if policy.specialist_mode:
        flags.append("specialists")
    if not policy.verification_required:
        flags.append("no_verify")
    if policy.public_posting:
        flags.append("public_post")
    return ", ".join(flags) if flags else "defaults"


class RepositoriesPanel(Widget):
    DEFAULT_CSS = """
    RepositoriesPanel {
        padding: 1 2;
    }

    RepositoriesPanel .repositories-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        snapshot: InstallationSnapshot,
        *,
        repo_config: RepoConfigStore | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._snapshot = snapshot
        self._repo_config = repo_config

    def compose(self) -> ComposeResult:
        repo_ids = [repo.github_repository_id for repo in self._snapshot.repositories]
        policies = (
            self._repo_config.all_for(repo_ids)
            if self._repo_config is not None
            else {repo_id: default_review_policy() for repo_id in repo_ids}
        )
        yield Vertical(
            Label("Repositories", classes="repositories-heading", id="repositories-heading"),
            *[
                Static(
                    (
                        f"{repo.name} ({repo.github_repository_id})"
                        f" - {format_policy_summary(policies[repo.github_repository_id])}"
                    ),
                    classes="repository-row",
                    id=f"repo-{repo.github_repository_id}",
                )
                for repo in self._snapshot.repositories
            ],
            id="repositories-panel",
        )
