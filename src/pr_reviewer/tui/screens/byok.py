"""BYOK screen: hidden key entry and an immediate provider check."""

from __future__ import annotations

from typing import Protocol

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static

from pr_reviewer.models.catalogue import list_providers
from pr_reviewer.models.provider import ModelKeyInvalid, ModelProviderFailure, ModelVendor
from pr_reviewer.runner.secrets import SecretStore
from pr_reviewer.tui.auth_state import MODEL_KEY_SECRET


class ModelKeyChecker(Protocol):
    def __call__(self, provider_id: ModelVendor, api_key: str) -> None: ...


class ModelKeyStored(Message):
    """Posted after a key passes the live check and is saved locally."""


def default_model_key_checker(provider_id: ModelVendor, api_key: str) -> None:
    from pr_reviewer.models.provider import verify_provider_api_key

    verify_provider_api_key(provider_id, api_key)


class ByokPanel(Widget):
    """Collect a provider API key with hidden input and verify it immediately."""

    DEFAULT_CSS = """
    ByokPanel {
        padding: 1 2;
    }

    ByokPanel .byok-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ByokPanel .byok-status--ok {
        color: $success;
    }

    ByokPanel .byok-status--error {
        color: $error;
    }
    """

    check_status: reactive[str] = reactive("")

    def __init__(
        self,
        *,
        secrets: SecretStore,
        key_checker: ModelKeyChecker | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._secrets = secrets
        self._key_checker = key_checker or default_model_key_checker
        provider_options = [(provider.label, provider.provider_id) for provider in list_providers()]
        self._provider_options = provider_options
        self._default_provider = provider_options[0][1] if provider_options else "openai"

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Bring your own model key", classes="byok-heading", id="byok-heading"),
            Static(
                "Keys stay on this machine and never reach Neon.",
                id="byok-privacy",
            ),
            Select(
                self._provider_options,
                id="byok-provider",
                value=self._default_provider,
            ),
            Input(
                placeholder="Paste your API key",
                password=True,
                id="byok-key-input",
            ),
            Button("Save and verify", id="byok-save", variant="primary"),
            Static("", id="byok-status"),
            id="byok-panel",
        )

    def watch_check_status(self, status: str) -> None:
        widget = self.query_one("#byok-status", Static)
        widget.update(status)
        widget.set_class(status.startswith("Key saved"), "byok-status--ok")
        widget.set_class(
            status.startswith("Key rejected") or status.startswith("Could not verify"),
            "byok-status--error",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "byok-save":
            return
        provider_id = str(self.query_one("#byok-provider", Select).value)
        api_key = self.query_one("#byok-key-input", Input).value.strip()
        if not api_key:
            self.check_status = "Enter an API key first."
            return
        try:
            self._key_checker(provider_id, api_key)  # type: ignore[arg-type]
        except ModelKeyInvalid:
            self.check_status = "Key rejected by the provider."
            return
        except ModelProviderFailure:
            self.check_status = "Could not verify the key right now."
            return
        self._secrets.set(MODEL_KEY_SECRET, api_key)
        self.query_one("#byok-key-input", Input).value = ""
        self.check_status = "Key saved."
        self.post_message(ModelKeyStored())
