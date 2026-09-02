"""Model access screen: API keys only for now, shaped for more methods later."""

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

ACCESS_METHODS: tuple[dict[str, str], ...] = (
    {"id": "api_key", "label": "API key", "kind": "api_key"},
)


class ModelKeyChecker(Protocol):
    def __call__(self, provider_id: ModelVendor, api_key: str) -> None: ...


class ModelKeyStored(Message):
    """Posted after a key passes the live check and is saved locally."""


def default_model_key_checker(provider_id: ModelVendor, api_key: str) -> None:
    from pr_reviewer.models.provider import verify_provider_api_key

    verify_provider_api_key(provider_id, api_key)


class ModelAccessPanel(Widget):
    """Collect a provider API key with hidden input and verify it immediately."""

    DEFAULT_CSS = """
    ModelAccessPanel {
        padding: 1 2;
    }

    ModelAccessPanel .model-access-heading {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ModelAccessPanel .model-access-status--ok {
        color: $success;
    }

    ModelAccessPanel .model-access-status--error {
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
        self._access_method = ACCESS_METHODS[0]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Model access", classes="model-access-heading", id="model-access-heading"),
            Static(
                "Keys stay on this machine and never reach the hosted plane.",
                id="model-access-privacy",
            ),
            Static(self._access_method["label"], id="model-access-method"),
            Select(
                self._provider_options,
                id="model-access-provider",
                value=self._default_provider,
            ),
            Input(
                placeholder="Paste your API key",
                password=True,
                id="model-access-key-input",
            ),
            Button("Save and verify", id="model-access-save", variant="primary"),
            Static("", id="model-access-status"),
            id="model-access-panel",
        )

    def watch_check_status(self, status: str) -> None:
        widget = self.query_one("#model-access-status", Static)
        widget.update(status)
        widget.set_class(status.startswith("Key saved"), "model-access-status--ok")
        widget.set_class(
            status.startswith("Key rejected") or status.startswith("Could not verify"),
            "model-access-status--error",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "model-access-save":
            return
        provider_id = str(self.query_one("#model-access-provider", Select).value)
        api_key = self.query_one("#model-access-key-input", Input).value.strip()
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
        self.query_one("#model-access-key-input", Input).value = ""
        self.check_status = "Key saved."
        self.post_message(ModelKeyStored())
