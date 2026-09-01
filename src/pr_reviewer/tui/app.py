"""Bare `reviewer` opens this Textual app instead of dumping usage."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static

from pr_reviewer.local_store.repo_config import RepoConfigStore, default_repo_config_path
from pr_reviewer.runner.secrets import SecretStore, get_secret_store
from pr_reviewer.tui.auth_state import RUNNER_CREDENTIAL_SECRET, is_github_connected
from pr_reviewer.tui.installation_client import HostedInstallationClient, InstallationClient
from pr_reviewer.tui.installation_snapshot import (
    InstallationSnapshot,
    default_snapshot_path,
    load_installation_snapshot,
    save_installation_snapshot,
)
from pr_reviewer.tui.nav import SectionNav, SectionSelected
from pr_reviewer.tui.pairing_client import PairingClient
from pr_reviewer.tui.screens.connect import ConnectPanel, can_start_review
from pr_reviewer.tui.screens.profile import ProfilePanel
from pr_reviewer.tui.screens.repositories import RepositoriesPanel
from pr_reviewer.tui.theme import REVIEWER_CSS, REVIEWER_THEME


class ReviewerApp(App[None]):
    TITLE = "reviewer"
    CSS = REVIEWER_CSS

    def __init__(
        self,
        *,
        secrets: SecretStore | None = None,
        pairing_client: PairingClient | None = None,
        installation_client: InstallationClient | None = None,
        installation_snapshot: InstallationSnapshot | None = None,
        repo_config: RepoConfigStore | None = None,
        config_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.register_theme(REVIEWER_THEME)
        self.theme = REVIEWER_THEME.name
        self._config_dir = config_dir or (Path.home() / ".config" / "pr-reviewer")
        self._secrets = secrets or get_secret_store(file_fallback_directory=self._config_dir)
        self._pairing_client = pairing_client
        self._installation_client = installation_client or HostedInstallationClient()
        self._installation_snapshot = installation_snapshot
        self._repo_config = repo_config or RepoConfigStore(
            default_repo_config_path(self._config_dir)
        )

    @property
    def github_connected(self) -> bool:
        return is_github_connected(self._secrets)

    def compose(self) -> ComposeResult:
        if self.github_connected:
            yield Horizontal(
                SectionNav(id="section-nav"),
                Container(id="section-content"),
                id="main-layout",
            )
            return

        yield Horizontal(
            SectionNav(id="section-nav"),
            ConnectPanel(pairing_client=self._pairing_client, id="connect-screen"),
            id="main-layout",
        )

    def on_mount(self) -> None:
        if not self.github_connected:
            return
        snapshot = self._resolve_installation_snapshot()
        if snapshot is None:
            self.query_one("#section-content", Container).mount(
                Static("Installation details are not available yet.", id="installation-missing")
            )
            return
        self._show_section("repositories", snapshot)

    def on_section_selected(self, message: SectionSelected) -> None:
        if message.section_id == "reviews" and not can_start_review(self.github_connected):
            self.notify("Connect GitHub before starting a review.", severity="warning")
            return
        if not self.github_connected:
            return
        snapshot = self._resolve_installation_snapshot()
        if snapshot is None:
            return
        self._show_section(message.section_id, snapshot)

    def _resolve_installation_snapshot(self) -> InstallationSnapshot | None:
        if self._installation_snapshot is not None:
            return self._installation_snapshot

        snapshot_path = default_snapshot_path(self._config_dir)
        cached = load_installation_snapshot(snapshot_path)
        credential = self._secrets.get(RUNNER_CREDENTIAL_SECRET)
        hosted_origin = _hosted_origin_from_env()
        if credential and hosted_origin is not None:
            try:
                fetched = self._installation_client.fetch(hosted_origin, credential)
            except Exception:
                return cached
            save_installation_snapshot(snapshot_path, fetched)
            self._installation_snapshot = fetched
            return fetched
        return cached

    def _show_section(self, section_id: str, snapshot: InstallationSnapshot) -> None:
        pane = self.query_one("#section-content", Container)
        pane.remove_children()
        if section_id == "profile":
            pane.mount(ProfilePanel(snapshot))
            return
        if section_id == "repositories":
            pane.mount(RepositoriesPanel(snapshot, repo_config=self._repo_config))
            return
        pane.mount(Static(section_id, id="section-placeholder"))


def _hosted_origin_from_env() -> str | None:
    import os

    origin = os.environ.get("PR_REVIEWER_HOSTED_ORIGIN", "").strip().rstrip("/")
    if origin.startswith("https://"):
        return origin
    return None


def run_tui() -> int:
    ReviewerApp().run()
    return 0
