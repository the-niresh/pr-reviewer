"""GitHub connect screen: one sign-in action and unattended pairing wait."""

from __future__ import annotations

import hashlib
import secrets
import socket
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from pr_reviewer.tui.github_connect import (
    HostedOriginError,
    build_github_sign_in_url,
    hosted_origin_from_env,
)
from pr_reviewer.tui.pairing_client import PairingClient
from pr_reviewer.tui.pairing_wait import (
    LocalPairingStatusClient,
    PairingWaitDeadlineExceeded,
    wait_for_pairing,
)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


class ConnectPanel(Widget):
    """Offer sign in, open the browser, and wait for pairing without user copying."""

    DEFAULT_CSS = """
    ConnectPanel {
        padding: 1 2;
    }

    ConnectPanel .connect-heading {
        text-style: bold;
        color: $accent;
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
        browser_opener: Callable[[str], None] | None = None,
        pairing_poll_interval: float = 2.0,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._config = config
        self._pairing_client = pairing_client
        self._local_status_client = local_status_client
        self._browser_opener = browser_opener or webbrowser.open
        self._pairing_poll_interval = pairing_poll_interval
        self._verifier = secrets.token_urlsafe(32)
        self._challenge = sha256_hex(self._verifier)
        self._pairing_code = ""
        self._poll_timer: Any = None

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
        widget.update(f"Pairing status: {status}")
        widget.set_class(status == "exchangeable", "pairing-status--exchangeable")
        widget.set_class(status.startswith("pairing failed"), "pairing-status--error")

    def _start_sign_in(self) -> None:
        if self._pairing_code:
            return
        try:
            config = self._config or ConnectConfig(
                hosted_origin=hosted_origin_from_env(),
                device_name=_default_device_name(),
            )
        except HostedOriginError as exc:
            self.pairing_status = f"pairing failed: {exc}"
            return

        if self._pairing_client is None:
            from pr_reviewer.tui.pairing_client import HostedPairingClient

            self._pairing_client = HostedPairingClient(config.hosted_origin)

        try:
            self._pairing_code = self._pairing_client.create_code(
                config.device_name,
                self._challenge,
            )
        except Exception as exc:  # noqa: BLE001 - surface hosted errors in the TUI
            self.pairing_status = f"pairing failed: {exc}"
            return

        sign_in_url = build_github_sign_in_url(config.hosted_origin)
        self._browser_opener(sign_in_url)
        self.pairing_status = "pending"
        if self._local_status_client is not None:
            self._poll_timer = self.set_interval(
                self._pairing_poll_interval,
                self._poll_pairing_status,
            )

    def _poll_pairing_status(self) -> None:
        if not self._pairing_code or self._local_status_client is None:
            return
        try:
            wait_for_pairing(
                code=self._pairing_code,
                challenge=self._challenge,
                status_client=self._local_status_client,
                deadline_seconds=self._pairing_poll_interval + 0.001,
                poll_interval_seconds=0.0,
                sleep=lambda _seconds: None,
            )
        except PairingWaitDeadlineExceeded:
            return
        self._stop_polling()
        self.pairing_status = "exchangeable"
        self.post_message(PairingExchangeable(self._pairing_code, self._verifier))

    def _stop_polling(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None


def _default_device_name() -> str:
    return socket.gethostname() or "reviewer-tui"


def can_start_review(connected: bool, *, model_key_present: bool = True) -> bool:
    return connected and model_key_present
