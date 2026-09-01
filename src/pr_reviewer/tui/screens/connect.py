"""GitHub connect screen: URLs, pairing code, and status polling."""

from __future__ import annotations

import hashlib
import secrets
import socket
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static

from pr_reviewer.tui.github_connect import (
    HostedOriginError,
    app_slug_from_env,
    build_github_connect_urls,
    hosted_origin_from_env,
)
from pr_reviewer.tui.pairing_client import PairingClient


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConnectConfig:
    hosted_origin: str
    app_slug: str
    device_name: str


class PairingExchangeable(Message):
    """Posted when the hosted pairing code becomes exchangeable."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__()


class ConnectPanel(Widget):
    """Show hosted GitHub links and wait for pairing approval."""

    DEFAULT_CSS = """
    ConnectPanel {
        padding: 1 2;
    }

    ConnectPanel .connect-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ConnectPanel .connect-url {
        color: $primary;
        margin-bottom: 1;
    }

    ConnectPanel .pairing-status--exchangeable {
        color: $success;
        text-style: bold;
    }
    """

    pairing_status: reactive[str] = reactive("starting")

    def __init__(
        self,
        *,
        config: ConnectConfig | None = None,
        pairing_client: PairingClient | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._config = config
        self._pairing_client = pairing_client
        self._verifier = secrets.token_urlsafe(32)
        self._challenge = sha256_hex(self._verifier)
        self._pairing_code = ""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("GitHub is not connected", classes="connect-heading", id="connect-heading"),
            Static("No GitHub connection means no review.", id="connect-refusal"),
            Static("", id="install-url", classes="connect-url"),
            Static("", id="sign-in-url", classes="connect-url"),
            Static("", id="pairing-code"),
            Static("starting", id="pairing-status"),
            id="connect-panel",
        )

    def on_mount(self) -> None:
        try:
            config = self._config or ConnectConfig(
                hosted_origin=hosted_origin_from_env(),
                app_slug=app_slug_from_env(),
                device_name=_default_device_name(),
            )
        except HostedOriginError as exc:
            self.pairing_status = str(exc)
            self.query_one("#pairing-status", Static).update(str(exc))
            return

        install_url, sign_in_url = build_github_connect_urls(
            config.hosted_origin,
            app_slug=config.app_slug,
        )
        self.query_one("#install-url", Static).update(f"Install the App: {install_url}")
        self.query_one("#sign-in-url", Static).update(f"Sign in: {sign_in_url}")

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
            self.query_one("#pairing-status", Static).update(self.pairing_status)
            return

        self.query_one("#pairing-code", Static).update(f"Pairing code: {self._pairing_code}")
        self.pairing_status = "pending"
        self.set_interval(2.0, self._poll_pairing_status)

    def watch_pairing_status(self, status: str) -> None:
        widget = self.query_one("#pairing-status", Static)
        widget.update(f"Pairing status: {status}")
        widget.set_class(status == "exchangeable", "pairing-status--exchangeable")

    def _poll_pairing_status(self) -> None:
        if self._pairing_client is None or not self._pairing_code:
            return
        status = self._pairing_client.status(self._pairing_code, self._challenge)
        self.pairing_status = status
        if status == "exchangeable":
            self.post_message(PairingExchangeable(self._pairing_code))


def _default_device_name() -> str:
    return socket.gethostname() or "reviewer-tui"


def can_start_review(connected: bool, *, model_key_present: bool = True) -> bool:
    return connected and model_key_present
