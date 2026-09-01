"""Repositories screen listing installation-permitted repositories."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from pr_reviewer.tui.installation_snapshot import InstallationSnapshot


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

    def __init__(self, snapshot: InstallationSnapshot, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._snapshot = snapshot

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Repositories", classes="repositories-heading", id="repositories-heading"),
            *[
                Static(
                    f"{repo.name} ({repo.github_repository_id})",
                    classes="repository-row",
                    id=f"repo-{repo.github_repository_id}",
                )
                for repo in self._snapshot.repositories
            ],
            id="repositories-panel",
        )
