"""Provider API key entry in the terminal."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pr_reviewer.runner.secrets import FileSecretStore
from pr_reviewer.tui.auth_state import MODEL_KEY_SECRET, has_model_key
from pr_reviewer.tui.screens.connect import can_start_review
from pr_reviewer.tui.screens.model_access import (
    ACCESS_METHODS,
    ModelAccessPanel,
    ModelKeyStored,
)

API_KEY = "sk-model-access-test-key"


def test_access_methods_ship_api_key_only() -> None:
    assert tuple(method["id"] for method in ACCESS_METHODS) == ("api_key",)


def test_unset_key_does_not_start_review() -> None:
    assert can_start_review(True, model_key_present=False) is False


def test_model_access_panel_uses_hidden_input() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Input

        secrets = FileSecretStore(Path("/tmp/pr-reviewer-model-access-hidden"))

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ModelAccessPanel(secrets=secrets, key_checker=lambda *_: None)

        async with Harness().run_test() as pilot:
            field = pilot.app.query_one("#model-access-key-input", Input)
            assert field.password is True


    asyncio.run(exercise())


def test_model_access_stores_key_after_verify() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        secrets = FileSecretStore(Path("/tmp/pr-reviewer-model-access-store"))
        stored: list[str] = []

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ModelAccessPanel(
                    secrets=secrets,
                    key_checker=lambda _provider, _key: None,
                )

            def on_model_key_stored(self, _message: ModelKeyStored) -> None:
                stored.append("stored")

        async with Harness().run_test() as pilot:
            pilot.app.query_one("#model-access-key-input").value = API_KEY
            await pilot.click("#model-access-save")
            assert stored == ["stored"]
            assert has_model_key(secrets)
            assert secrets.get(MODEL_KEY_SECRET) == API_KEY

    asyncio.run(exercise())
