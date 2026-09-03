"""Bare `reviewer` opens this Textual app instead of dumping usage."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Footer, Static

from pr_reviewer.local_store.repo_config import RepoConfigStore, default_repo_config_path
from pr_reviewer.local_store.review_log import ReviewLogStore, default_review_log_path
from pr_reviewer.runner.client import RunnerClient
from pr_reviewer.runner.secrets import SecretStore, get_secret_store
from pr_reviewer.tui.auth_state import RUNNER_CREDENTIAL_SECRET, has_model_key, is_github_connected
from pr_reviewer.tui.auto_review import (
    TUI_CLOSED_AUTO_REVIEW_MESSAGE,
    AutoReviewCoordinator,
    AutoReviewEventSource,
    AutoReviewOutcome,
    PullRequestSyncEvent,
)
from pr_reviewer.tui.github_reads import InstallationRepositoriesReader, OpenPullRequestsReader
from pr_reviewer.tui.installation_client import HostedInstallationClient, InstallationClient
from pr_reviewer.tui.installation_snapshot import (
    InstallationSnapshot,
    default_snapshot_path,
    load_installation_snapshot,
    save_installation_snapshot,
)
from pr_reviewer.tui.logout import log_out
from pr_reviewer.tui.nav import SECTIONS, SectionNav, SectionSelected
from pr_reviewer.tui.pairing_client import PairingClient
from pr_reviewer.tui.pairing_wait import LocalPairingStatusClient
from pr_reviewer.tui.review_dashboard import ReviewDashboardPanel, dashboard_repositories_from_log
from pr_reviewer.tui.screens.confirm import ConfirmScreen
from pr_reviewer.tui.screens.connect import ConnectPanel, PairingExchangeable, can_start_review
from pr_reviewer.tui.screens.model_access import ModelAccessPanel, ModelKeyStored
from pr_reviewer.tui.screens.profile import ProfilePanel
from pr_reviewer.tui.screens.prompts import AgentPromptsPanel
from pr_reviewer.tui.screens.repositories import PullRequestSelected, RepositoriesPanel
from pr_reviewer.tui.screens.review import ReviewDiffItem, ReviewPanel
from pr_reviewer.tui.theme import REVIEWER_CSS, REVIEWER_THEME


class MainLayout(Horizontal):
    """Holds the sidebar and the content pane.

    Screen binds tab/shift+tab to its own app.focus_next/focus_previous (see
    textual/screen.py), and that binding sits closer to a focused widget than the App's own
    BINDINGS -- so without this, tab only ever walks the flat, whole-app focus order and the
    App-level pane-switch actions below never run. Binding tab/shift+tab again here, one
    level above both panes, intercepts before Screen's default and makes the crossing
    pane-aware instead of accidental.
    """

    BINDINGS = [
        ("tab", "app.focus_next_pane", "Next pane"),
        ("shift+tab", "app.focus_previous_pane", "Prev pane"),
    ]


class ReviewerApp(App[None]):
    TITLE = "reviewer"
    CSS = REVIEWER_CSS

    # tab/shift+tab already move focus between widgets (Screen binds them to
    # app.focus_next/focus_previous), but that alone treats the sidebar and the content
    # pane as one flat list of buttons -- nothing marks "you just crossed into the other
    # pane". These bindings make that crossing a first-class, visible action: the footer
    # names every key, and the CSS above gives the pane that holds focus a heavy accent
    # border so the crossing is never only a hover effect.
    BINDINGS = [
        Binding("tab", "focus_next_pane", "Next pane", show=True),
        Binding("shift+tab", "focus_previous_pane", "Prev pane", show=True),
        Binding("down", "focus_down", "Down", show=True),
        Binding("up", "focus_up", "Up", show=True),
        Binding("enter", "activate_focused", "Open", show=True),
        Binding("escape", "go_back", "Back", show=True),
        Binding("1", "jump_section(0)", SECTIONS[0], show=True),
        Binding("2", "jump_section(1)", SECTIONS[1], show=True),
        Binding("3", "jump_section(2)", SECTIONS[2], show=True),
        Binding("4", "jump_section(3)", SECTIONS[3], show=True),
        Binding("question_mark", "show_help", "Help", show=True),
        Binding("l", "log_out", "Log out", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

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
        repositories_reader: InstallationRepositoriesReader | None = None,
        pull_requests_reader: OpenPullRequestsReader | None = None,
    ) -> None:
        super().__init__()
        self.register_theme(REVIEWER_THEME)
        self.theme = REVIEWER_THEME.name
        self._config_dir = config_dir or (Path.home() / ".config" / "pr-reviewer")
        self._secrets = secrets or get_secret_store(file_fallback_directory=self._config_dir)
        self._pairing_client = pairing_client
        self._installation_client = installation_client or HostedInstallationClient()
        self._installation_snapshot = installation_snapshot
        self._installation_problem = "Installation details are not available yet."
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
        # Deliberately no HttpLocalPairingStatusClient default: that pointed sign-in at the
        # local daemon on 127.0.0.1:8742, which is not running when a new user first types
        # `reviewer`. Left as None, ConnectPanel polls the hosted plane, which is where the
        # pairing state lives and which is reachable before any local setup exists.
        self._local_pairing_status_client = local_pairing_status_client
        self._pairing_poll_interval = pairing_poll_interval
        self._browser_opener = browser_opener
        self._repositories_reader = repositories_reader
        self._pull_requests_reader = pull_requests_reader

    @property
    def github_connected(self) -> bool:
        return is_github_connected(self._secrets)

    @property
    def model_key_configured(self) -> bool:
        return has_model_key(self._secrets)

    def compose(self) -> ComposeResult:
        if self.github_connected:
            yield MainLayout(
                SectionNav(id="section-nav"),
                Container(id="section-content"),
                id="main-layout",
            )
            yield Footer()
            return

        yield MainLayout(
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
        yield Footer()

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
        # self._pairing_client is a test-injection seam, not the client that ran this
        # pairing attempt: in real use it is None and ConnectPanel built its own
        # HostedPairingClient, which lives on that widget, not on this App. Reusing it
        # here would need a widget reference this handler has no business holding, so a
        # fresh client for the same hosted_origin is built instead -- message.hosted_origin
        # exists on PairingExchangeable for exactly this.
        if self._pairing_client is not None:
            client = self._pairing_client
        else:
            from pr_reviewer.tui.pairing_client import HostedPairingClient

            client = HostedPairingClient(message.hosted_origin)
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


    def on_pull_request_selected(self, message: PullRequestSelected) -> None:
        snapshot = self._resolve_installation_snapshot()
        if snapshot is None:
            return
        self.query_one(SectionNav).current_section = "reviews"
        self._show_section(
            "reviews",
            snapshot,
            review_id=f"pr-{message.pull_request_number}",
        )

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
            # Leaving whichever section was on screen before looked identical to this
            # section having loaded and having nothing to show -- the whole point of
            # _installation_problem is to say why, not to be read only on first connect.
            pane = self.query_one("#section-content", Container)
            pane.remove_children()
            pane.mount(Static(self._installation_problem, id="installation-missing"))
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
                Static(self._installation_problem, id="installation-missing")
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
        if not credential:
            self._installation_problem = "This terminal is not paired yet. Sign in to connect it."
            return cached
        if hosted_origin is None:
            self._installation_problem = "No hosted plane is configured for this terminal."
            return cached
        try:
            fetched = self._installation_client.fetch(hosted_origin, credential)
        except Exception as exc:  # noqa: BLE001 - every failure has to reach the screen in words
            # A stored credential the hosted plane rejects is the trap worth naming: the app
            # treats a credential's mere presence as "connected", so every section rendered
            # empty and the user had no way to learn the pairing had lapsed.
            if "401" in str(exc) or "unknown_credential" in str(exc):
                self._installation_problem = (
                    "This terminal's pairing is no longer recognised by reviewer.niresh.tech. "
                    "Sign in again to re-pair it."
                )
            else:
                self._installation_problem = f"Could not reach reviewer.niresh.tech ({exc})."
            return cached
        save_installation_snapshot(snapshot_path, fetched)
        self._installation_snapshot = fetched
        return fetched

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
            pane.mount(
                RepositoriesPanel(
                    snapshot.installation_id,
                    repositories_reader=self._repositories_reader,
                    pull_requests_reader=self._pull_requests_reader,
                    
                )
            )
            return
        if section_id == "agent-prompts":
            pane.mount(AgentPromptsPanel(snapshot, repo_config=self._repo_config))
            return
        if section_id == "reviews":
            if review_id != "live-review":
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
            pane.mount(
                ReviewDashboardPanel(
                    dashboard_repositories_from_log(snapshot, self._review_log),
                    id="reviews-dashboard",
                )
            )
            return
        pane.mount(Static(section_id, id="section-placeholder"))

    # -- keyboard model: move focus between the sidebar and the content pane, move within
    # whichever pane holds focus, jump straight to a section, and help/quit. tab/shift+tab
    # already move focus widget-by-widget (Screen binds those to focus_next/focus_previous),
    # but that treats the whole app as one flat list -- these actions instead treat the
    # sidebar and the content pane as exactly two panes, and only ever move within or
    # between those two, so "which pane is live" stays a deliberate, visible choice (see the
    # :focus-within borders in theme.py and nav.py) rather than an accident of tab order.

    def _panes(self) -> tuple[Widget, Widget] | None:
        try:
            nav = self.query_one("#section-nav", Widget)
            content = self.query_one("#section-content", Widget)
        except NoMatches:
            return None
        return nav, content

    def _focusables(self, pane: Widget) -> list[Widget]:
        return [widget for widget in pane.query("*") if widget.can_focus]

    def _pane_holding_focus(self) -> Widget | None:
        panes = self._panes()
        focused = self.focused
        if panes is None or focused is None:
            return None
        for pane in panes:
            if any(focused is widget for widget in pane.query("*")):
                return pane
        return None

    def action_focus_next_pane(self) -> None:
        self._switch_pane()

    def action_focus_previous_pane(self) -> None:
        self._switch_pane()

    def _switch_pane(self) -> None:
        panes = self._panes()
        if panes is None:
            return
        nav, content = panes
        current = self._pane_holding_focus()
        target = content if current is nav else nav
        focusables = self._focusables(target)
        if focusables:
            focusables[0].focus()

    def action_focus_down(self) -> None:
        self._move_within_pane(1)

    def action_focus_up(self) -> None:
        self._move_within_pane(-1)

    def _move_within_pane(self, offset: int) -> None:
        pane = self._pane_holding_focus()
        if pane is None:
            return
        focusables = self._focusables(pane)
        if not focusables:
            return
        focused = self.focused
        try:
            index = next(i for i, widget in enumerate(focusables) if widget is focused)
        except StopIteration:
            index = 0
        focusables[(index + offset) % len(focusables)].focus()

    def action_activate_focused(self) -> None:
        focused = self.focused
        if focused is not None and hasattr(focused, "press"):
            focused.press()

    def action_go_back(self) -> None:
        panes = self._panes()
        if panes is None:
            return
        try:
            dashboard = self.query_one(ReviewDashboardPanel)
        except NoMatches:
            dashboard = None
        if dashboard is not None and dashboard.back_to_table():
            return
        nav, _content = panes
        focusables = self._focusables(nav)
        if focusables:
            focusables[0].focus()

    def action_jump_section(self, index: int) -> None:
        if not 0 <= index < len(SECTIONS):
            return
        try:
            self.query_one(SectionNav).select_section(SECTIONS[index])
        except NoMatches:
            return

    def action_show_help(self) -> None:
        self.notify(
            "tab/shift+tab: switch pane  up/down: move  enter: open  escape: back to nav  "
            "1-4: jump to a section  l: log out  q: quit",
            title="Keys",
            timeout=8,
        )

    def action_log_out(self) -> None:
        if not self.github_connected:
            self.notify("Not signed in.", severity="warning")
            return
        # Revoking is not something a stray keypress or an accidental click on the
        # footer's own "Log out" hint gets to do by itself: pairing.py has no way to
        # un-revoke a runner, so this session is genuinely gone once confirmed.
        # push_screen's own wait_for_dismiss=True requires running inside a worker,
        # which an action is not, so the continuation is a callback instead.
        self.push_screen(
            ConfirmScreen(
                "Log out of this terminal? You will need to sign in again to review.",
                confirm_label="Log out",
            ),
            self._log_out_if_confirmed,
        )

    async def _log_out_if_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        credential = self._secrets.get(RUNNER_CREDENTIAL_SECRET)
        hosted_origin = _hosted_origin_from_env()
        runner_client: RunnerClient | None = None
        if credential and hosted_origin:
            runner_client = RunnerClient(hosted_origin, credential)
        log_out(self._secrets, runner_client=runner_client)
        # The cached snapshot names the installation and repositories the credential just
        # deleted was scoped to -- leaving it on disk would show a signed-out terminal
        # someone else's profile and repository list the moment they pair a new account.
        default_snapshot_path(self._config_dir).unlink(missing_ok=True)
        self._stop_auto_review()
        self.notify("Signed out.")
        await self.recompose()


def _hosted_origin_from_env() -> str | None:
    """The hosted origin this runner talks to, defaulting to production.

    This used to read PR_REVIEWER_HOSTED_ORIGIN and return None when it was unset. A real
    install never sets it, so the snapshot fetch was skipped, the cached snapshot did not
    exist either, and every section rendered "Installation details are not available yet."
    """
    from pr_reviewer.tui.github_connect import HostedOriginError, resolved_hosted_origin

    try:
        return resolved_hosted_origin()
    except HostedOriginError:
        return None


def run_tui() -> int:
    app = ReviewerApp()
    app.run()
    if app._auto_review_was_running:
        print(TUI_CLOSED_AUTO_REVIEW_MESSAGE, file=sys.stderr)
    return 0
