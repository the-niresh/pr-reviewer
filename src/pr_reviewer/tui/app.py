"""Bare `reviewer` opens this Textual app instead of dumping usage."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static

from pr_reviewer.local_store.repo_config import RepoConfigStore, default_repo_config_path
from pr_reviewer.local_store.review_log import ReviewLogStore, default_review_log_path
from pr_reviewer.runner.secrets import SecretStore, get_secret_store
from pr_reviewer.tui.auth_state import RUNNER_CREDENTIAL_SECRET, has_model_key, is_github_connected
from pr_reviewer.tui.auto_review import (
    TUI_CLOSED_AUTO_REVIEW_MESSAGE,
    AutoReviewCoordinator,
    AutoReviewEventSource,
    AutoReviewOutcome,
    PullRequestSyncEvent,
)
from pr_reviewer.tui.installation_client import HostedInstallationClient, InstallationClient
from pr_reviewer.tui.installation_snapshot import (
    InstallationSnapshot,
    default_snapshot_path,
    load_installation_snapshot,
    save_installation_snapshot,
)
from pr_reviewer.tui.nav import SECTIONS, SectionNav, SectionSelected
from pr_reviewer.tui.pairing_client import PairingClient
from pr_reviewer.tui.pairing_wait import HttpLocalPairingStatusClient, LocalPairingStatusClient
from pr_reviewer.tui.screens.connect import ConnectPanel, PairingExchangeable, can_start_review
from pr_reviewer.tui.screens.model_access import ModelAccessPanel, ModelKeyStored
from pr_reviewer.tui.screens.profile import ProfilePanel
from pr_reviewer.tui.screens.prompts import AgentPromptsPanel
from pr_reviewer.tui.screens.repositories import RepositoriesPanel
from pr_reviewer.tui.screens.review import ReviewDiffItem, ReviewPanel
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
        review_log: ReviewLogStore | None = None,
        config_dir: Path | None = None,
        auto_review_event_source: AutoReviewEventSource | None = None,
        auto_review_poll_interval: float = 1.0,
        local_pairing_status_client: LocalPairingStatusClient | None = None,
        pairing_poll_interval: float = 2.0,
        browser_opener: Callable[[str], None] | None = None,
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
        self._review_log = review_log or ReviewLogStore(
            default_review_log_path(self._config_dir)
        )
        self._auto_review_event_source = auto_review_event_source
        self._auto_review_poll_interval = auto_review_poll_interval
        self._auto_review = AutoReviewCoordinator(on_start_review=self._on_auto_review_start)
        self._auto_review_timer: Any = None
        self._auto_review_was_running = False
        self._local_pairing_status_client = (
            local_pairing_status_client or HttpLocalPairingStatusClient()
        )
        self._pairing_poll_interval = pairing_poll_interval
        self._browser_opener = browser_opener

    @property
    def github_connected(self) -> bool:
        return is_github_connected(self._secrets)

    @property
    def model_key_configured(self) -> bool:
        return has_model_key(self._secrets)

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
            ConnectPanel(
                pairing_client=self._pairing_client,
                local_status_client=self._local_pairing_status_client,
                browser_opener=self._browser_opener,
                pairing_poll_interval=self._pairing_poll_interval,
                id="connect-screen",
            ),
            id="main-layout",
        )

    def on_mount(self) -> None:
        if not self.github_connected:
            return
        if not self.model_key_configured:
            self._mount_model_access_panel()
            return
        self._mount_default_section()
        self._start_auto_review()

    def on_unmount(self) -> None:
        self._stop_auto_review()


    def on_pairing_exchangeable(self, message: PairingExchangeable) -> None:
        client = self._pairing_client
        if client is None:
            return
        credential = client.exchange(message.code, message.verifier)
        self._secrets.set(RUNNER_CREDENTIAL_SECRET, credential)
        self._rebuild_after_pairing()

    def _rebuild_after_pairing(self) -> None:
        layout = self.query_one("#main-layout")
        self.query_one("#connect-screen").remove()
        layout.mount(Container(id="section-content"))
        if not self.model_key_configured:
            self._mount_model_access_panel()
            return
        self._mount_default_section()
        self._start_auto_review()

    def on_model_key_stored(self, _message: ModelKeyStored) -> None:
        pane = self.query_one("#section-content", Container)
        pane.remove_children()
        self._mount_default_section()
        self._start_auto_review()

    def on_section_selected(self, message: SectionSelected) -> None:
        if message.section_id == "reviews" and not can_start_review(
            self.github_connected,
            model_key_present=self.model_key_configured,
        ):
            if not self.github_connected:
                self.notify("Connect GitHub before starting a review.", severity="warning")
            else:
                self.notify("Add a model key before starting a review.", severity="warning")
            return
        if not self.github_connected or not self.model_key_configured:
            return
        snapshot = self._resolve_installation_snapshot()
        if snapshot is None:
            return
        self._show_section(message.section_id, snapshot)

    def _mount_model_access_panel(self) -> None:
        self.query_one("#section-content", Container).mount(
            ModelAccessPanel(secrets=self._secrets, id="model-access-screen")
        )

    def _mount_default_section(self) -> None:
        snapshot = self._resolve_installation_snapshot()
        if snapshot is None:
            self.query_one("#section-content", Container).mount(
                Static("Installation details are not available yet.", id="installation-missing")
            )
            return
        self._show_section("repositories", snapshot)

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

    def _start_auto_review(self) -> None:
        if not self.github_connected or not self.model_key_configured:
            return
        if self._auto_review.running:
            return
        self._auto_review.start()
        self._auto_review_was_running = True
        if self._auto_review_event_source is None:
            return
        self._auto_review_timer = self.set_interval(
            self._auto_review_poll_interval,
            self._poll_auto_review_events,
        )

    def _stop_auto_review(self) -> None:
        if self._auto_review_timer is not None:
            self._auto_review_timer.stop()
            self._auto_review_timer = None
        if self._auto_review.running:
            self._auto_review.stop()

    def _poll_auto_review_events(self) -> None:
        if self._auto_review_event_source is None:
            return
        for event in self._auto_review_event_source.poll():
            self._auto_review.handle(event)

    def _on_auto_review_start(
        self,
        event: PullRequestSyncEvent,
        superseded: bool,
        _previous_head_sha: str,
    ) -> None:
        outcome = AutoReviewOutcome(
            kind="superseded" if superseded else "started",
            pull_request_number=event.pull_request_number,
            head_sha=event.head_sha,
        )
        self._show_auto_review(outcome)

    def _show_auto_review(self, outcome: AutoReviewOutcome) -> None:
        if outcome.kind not in {"started", "superseded"}:
            return
        message = f"Reviewing PR #{outcome.pull_request_number}"
        if outcome.kind == "superseded":
            message += " (superseded previous run)"
        self.notify(message)
        snapshot = self._resolve_installation_snapshot()
        if snapshot is None:
            return
        if "section-nav" in {widget.id for widget in self.query("#section-nav")}:
            # Set the reactive directly rather than select_section(): that also posts
            # SectionSelected, which on_section_selected would handle by calling
            # _show_section again with the default review_id, clobbering the
            # PR-scoped ReviewPanel this method is about to mount below.
            self.query_one(SectionNav).current_section = "reviews"
        self._show_section("reviews", snapshot, review_id=f"pr-{outcome.pull_request_number}")

    def _show_section(
        self,
        section_id: str,
        snapshot: InstallationSnapshot,
        *,
        review_id: str = "live-review",
    ) -> None:
        if section_id not in SECTIONS:
            pane = self.query_one("#section-content", Container)
            pane.remove_children()
            pane.mount(Static(section_id, id="section-placeholder"))
            return
        if section_id == "reviews" and (
            not self.github_connected or not self.model_key_configured
        ):
            return
        pane = self.query_one("#section-content", Container)
        pane.remove_children()
        if section_id == "profile":
            pane.mount(ProfilePanel(snapshot))
            return
        if section_id == "repositories":
            pane.mount(RepositoriesPanel(snapshot, repo_config=self._repo_config))
            return
        if section_id == "agent-prompts":
            pane.mount(AgentPromptsPanel(snapshot, repo_config=self._repo_config))
            return
        if section_id == "reviews":
            pane.mount(
                ReviewPanel(
                    (
                        ReviewDiffItem(
                            "app.py",
                            "@@ -1,1 +1,2 @@\n-old\n+new\n",
                        ),
                        ReviewDiffItem(
                            "README.md",
                            "@@ -1,1 +1,2 @@\n # Widgets\n+More docs\n",
                        ),
                    ),
                    review_log=self._review_log,
                    review_id=review_id,
                )
            )
            return
        pane.mount(Static(section_id, id="section-placeholder"))


def _hosted_origin_from_env() -> str | None:
    import os

    origin = os.environ.get("PR_REVIEWER_HOSTED_ORIGIN", "").strip().rstrip("/")
    if origin.startswith("https://"):
        return origin
    return None


def run_tui() -> int:
    app = ReviewerApp()
    app.run()
    if app._auto_review_was_running:
        print(TUI_CLOSED_AUTO_REVIEW_MESSAGE, file=sys.stderr)
    return 0
