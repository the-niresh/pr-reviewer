"""GitHub connect screen: Claude-Code-style device login.

Paste a link, confirm a short code, wait. The screen never launches a browser on its own
(headless boxes silently drop it, console browsers replace the TUI, and webbrowser.Error can
kill the app) and never blocks the UI thread on the hosted HTTP calls -- both the pairing-code
creation and the completion poll run on a Textual worker thread.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from pr_reviewer.tui.github_connect import (
    HostedOriginError,
    build_github_sign_in_url,
    resolved_hosted_origin,
)
from pr_reviewer.tui.pairing_client import PairingClient
from pr_reviewer.tui.pairing_wait import (
    LocalPairingStatusClient,
    PairingWaitDeadlineExceeded,
    wait_for_pairing,
)

# Bounded wait: the poll worker gives up and says so rather than spinning forever.
PAIRING_DEADLINE_SECONDS = 300.0

# webbrowser.get() names its console browsers after their binaries; none of these belong
# inside the TUI's own terminal, so "o" refuses to launch them.
CONSOLE_BROWSER_NAMES = frozenset({"lynx", "links", "elinks", "w3m", "www-browser"})

# A GUI browser is only plausible when something suggests a graphical session exists.
GUI_ENV_VARS = ("DISPLAY", "WAYLAND_DISPLAY", "BROWSER")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def gui_browser_plausible() -> bool:
    if not any(os.environ.get(name) for name in GUI_ENV_VARS):
        return False
    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return False
    name = (getattr(browser, "name", "") or "").lower()
    return name not in CONSOLE_BROWSER_NAMES


@dataclass(frozen=True)
class ConnectConfig:
    hosted_origin: str
    device_name: str


class PairingExchangeable(Message):
    """Posted when pairing completes and the runner credential can be exchanged."""

    def __init__(self, code: str, verifier: str) -> None:
        self.code = code
        self.verifier = verifier
        super().__init__()


class _SignInReady(Message):
    """Posted from the worker thread once the hosted plane hands back a pairing code."""

    def __init__(self, url: str, code: str) -> None:
        self.url = url
        self.code = code
        super().__init__()


class _SignInFailed(Message):
    """Posted from the worker thread: creating the code, or the wait, ended badly."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__()


class _PairingCompleted(Message):
    """Posted from the worker thread once the local daemon reports the code exchangeable."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__()


class ConnectPanel(Widget):
    """Show a sign-in link and pairing code, then wait for pairing without blocking the UI."""

    BINDINGS = [
        ("o", "open_browser", "Open browser"),
        ("c", "copy_link", "Copy link"),
    ]

    DEFAULT_CSS = """
    ConnectPanel {
        padding: 1 2;
    }

    ConnectPanel .connect-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ConnectPanel #sign-in-url {
        text-style: bold;
        color: $primary;
        margin-top: 1;
    }

    ConnectPanel #pairing-code {
        color: $secondary;
        margin-bottom: 1;
    }

    ConnectPanel .pairing-status--exchangeable {
        color: $success;
        text-style: bold;
    }

    ConnectPanel .pairing-status--error {
        color: $error;
    }
    """

    pairing_status: reactive[str] = reactive("not started")

    def __init__(
        self,
        *,
        config: ConnectConfig | None = None,
        pairing_client: PairingClient | None = None,
        local_status_client: LocalPairingStatusClient | None = None,
        browser_opener: Callable[[str], object] | None = None,
        pairing_poll_interval: float = 2.0,
        pairing_deadline_seconds: float = PAIRING_DEADLINE_SECONDS,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._config = config
        self._pairing_client = pairing_client
        self._local_status_client = local_status_client
        self._browser_opener = browser_opener or webbrowser.open
        self._pairing_poll_interval = pairing_poll_interval
        self._pairing_deadline_seconds = pairing_deadline_seconds
        self._verifier = secrets.token_urlsafe(32)
        self._challenge = sha256_hex(self._verifier)
        self._pairing_code = ""
        self._sign_in_url = ""
        self._sign_in_started = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("GitHub is not connected", classes="connect-heading", id="connect-heading"),
            Static("No GitHub connection means no review.", id="connect-refusal"),
            Button("Sign in", id="connect-sign-in", variant="primary"),
            Static("not started", id="pairing-status"),
            id="connect-panel",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect-sign-in":
            self._start_sign_in()

    def watch_pairing_status(self, status: str) -> None:
        widget = self.query_one("#pairing-status", Static)
        widget.update(status)
        widget.set_class(status == "signed in", "pairing-status--exchangeable")
        widget.set_class(status.startswith("pairing failed"), "pairing-status--error")

    def action_copy_link(self) -> None:
        if not self._sign_in_url:
            self.notify("No link yet -- press Sign in first.", severity="warning")
            return
        self.app.copy_to_clipboard(self._sign_in_url)
        self.notify("Link copied.", severity="information")

    def action_open_browser(self) -> None:
        if not self._sign_in_url:
            return
        if not gui_browser_plausible():
            self.notify(
                "No graphical browser detected here -- copy the link above instead.",
                severity="warning",
            )
            return
        try:
            opened = self._browser_opener(self._sign_in_url)
        except Exception as exc:  # noqa: BLE001 - a browser failure must never kill the TUI
            self.notify(f"Could not open a browser: {exc}", severity="warning")
            return
        if opened is False:
            self.notify(
                "No browser could be opened -- copy the link above instead.",
                severity="warning",
            )

    def _start_sign_in(self) -> None:
        if self._sign_in_started:
            return
        try:
            config = self._config or ConnectConfig(
                hosted_origin=resolved_hosted_origin(),
                device_name=_default_device_name(),
            )
        except HostedOriginError as exc:
            self.pairing_status = f"pairing failed: could not resolve the hosted origin ({exc})"
            return

        self._config = config
        if self._pairing_client is None:
            from pr_reviewer.tui.pairing_client import HostedPairingClient

            self._pairing_client = HostedPairingClient(config.hosted_origin)

        self._sign_in_started = True
        self.pairing_status = "creating a sign-in link..."
        self._run_sign_in(config.hosted_origin, config.device_name)

    @work(thread=True, exclusive=True)
    def _run_sign_in(self, hosted_origin: str, device_name: str) -> None:
        assert self._pairing_client is not None
        try:
            code = self._pairing_client.create_code(device_name, self._challenge)
        except Exception as exc:  # noqa: BLE001 - surface hosted errors in words, never a crash
            self.post_message(_SignInFailed(f"could not create a sign-in link ({exc})"))
            return

        try:
            url = build_github_sign_in_url(hosted_origin, pairing_code=code)
        except HostedOriginError as exc:
            self.post_message(_SignInFailed(f"could not build the sign-in link ({exc})"))
            return

        self.post_message(_SignInReady(url, code))

        # The hosted pairing client already satisfies the status protocol, and it is the
        # plane that actually owns the pairing state. Polling the local daemon on
        # 127.0.0.1:8742 instead made sign-in depend on a daemon the user has not started
        # yet, which is backwards: signing in is how they get set up in the first place.
        # A refused connection there raised httpx.ConnectError out of this worker and
        # Textual killed the app, right after the link appeared on screen.
        status_client = self._local_status_client or self._pairing_client
        try:
            wait_for_pairing(
                code=code,
                challenge=self._challenge,
                status_client=status_client,
                deadline_seconds=self._pairing_deadline_seconds,
                poll_interval_seconds=self._pairing_poll_interval,
            )
        except PairingWaitDeadlineExceeded as exc:
            # exc's own message already says which happened: the code was denied outright
            # (invalid, expired, or already used -- see pairing_wait.wait_for_pairing) or the
            # full deadline simply passed with nobody finishing in the browser. Either way the
            # wait has already stopped; this must not paper over that with a fixed message that
            # claims the full deadline elapsed when it did not.
            self.post_message(_SignInFailed(f"{exc} -- press Sign in to get a new link"))
            return
        except Exception as exc:  # noqa: BLE001 - nothing here may ever kill the TUI
            self.post_message(_SignInFailed(f"lost contact while waiting ({exc})"))
            return
        self.post_message(_PairingCompleted(code))

    def on__sign_in_ready(self, message: _SignInReady) -> None:
        self._sign_in_url = message.url
        self._pairing_code = message.code
        panel = self.query_one("#connect-panel", Vertical)
        status = self.query_one("#pairing-status", Static)
        panel.mount(Static(message.url, id="sign-in-url"), before=status)
        panel.mount(
            Static(
                f"Code: {message.code}  (press o to open in a browser, c to copy the link)",
                id="pairing-code",
            ),
            before=status,
        )
        self.pairing_status = "waiting for you to finish in the browser"

    def on__sign_in_failed(self, message: _SignInFailed) -> None:
        self._sign_in_started = False
        self.pairing_status = f"pairing failed: {message.reason}"

    def on__pairing_completed(self, message: _PairingCompleted) -> None:
        self.pairing_status = "signed in"
        # notify(), not just the status line's own colour: a toast is what actually catches
        # the eye the moment this arrives, and it clears itself after the timeout instead of
        # sitting there needing to be dismissed.
        self.notify("Signed in! Continuing...", severity="information", timeout=5)
        self.post_message(PairingExchangeable(message.code, self._verifier))


def _default_device_name() -> str:
    return socket.gethostname() or "reviewer-tui"


def can_start_review(connected: bool, *, model_key_present: bool = True) -> bool:
    return connected and model_key_present
