"""Profile screen showing the signed-in GitHub identity."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from pr_reviewer.tui.installation_snapshot import InstallationSnapshot


class ProfilePanel(Widget):
    DEFAULT_CSS = """
    ProfilePanel {
        padding: 1 2;
    }

    ProfilePanel .profile-heading {
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
            Label("GitHub profile", classes="profile-heading", id="profile-heading"),
            Static(f"login: {self._snapshot.github_login}", id="profile-login"),
            Static(
                f"github_user_id: {self._snapshot.github_user_id}",
                id="profile-user-id",
            ),
            Static(
                f"installation_id: {self._snapshot.installation_id}",
                id="profile-installation-id",
            ),
            id="profile-panel",
        )
