"""BYOK screen: hidden input and immediate provider key check."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from pr_reviewer.models.provider import (
    ModelKeyInvalid,
    ModelProviderFailure,
    verify_provider_api_key,
)
from pr_reviewer.runner.secrets import FileSecretStore
from pr_reviewer.tui.auth_state import MODEL_KEY_SECRET, has_model_key
from pr_reviewer.tui.screens.byok import ByokPanel, ModelKeyChecker
from pr_reviewer.tui.screens.connect import can_start_review
from pr_reviewer.tui.screens.model_access import ModelAccessPanel, ModelKeyStored

API_KEY = "sk-byok-test-must-not-appear-on-screen"


def test_can_start_review_requires_model_key() -> None:
    assert can_start_review(True, model_key_present=False) is False
    assert can_start_review(True, model_key_present=True) is True


def test_verify_provider_api_key_rejects_invalid_openai_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401, json={"error": {"message": "invalid"}})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.openai.com")
    try:
        with __import__("pytest").raises(ModelKeyInvalid):
            verify_provider_api_key("openai", API_KEY, http=client)
    finally:
        client.close()


def test_verify_provider_api_key_accepts_valid_openai_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://api.openai.com")
    try:
        verify_provider_api_key("openai", API_KEY, http=client)
    finally:
        client.close()


def test_byok_panel_uses_hidden_input() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Input

        secrets = FileSecretStore(Path("/tmp/pr-reviewer-byok-hidden"))

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ByokPanel(secrets=secrets, key_checker=lambda *_args: None)

        async with Harness().run_test() as pilot:
            field = pilot.app.query_one("#byok-key-input", Input)
            assert field.password is True

    asyncio.run(exercise())


def test_byok_panel_reports_bad_key_immediately() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Input

        secrets = FileSecretStore(Path("/tmp/pr-reviewer-byok-bad"))

        def reject(_provider: str, _key: str) -> None:
            raise ModelKeyInvalid()

        reject_checker: ModelKeyChecker = reject

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ByokPanel(secrets=secrets, key_checker=reject_checker)

        async with Harness().run_test() as pilot:
            
            field = pilot.app.query_one("#byok-key-input", Input)
            field.value = API_KEY
            await pilot.click("#byok-save")
            status = str(pilot.app.query_one("#byok-status").render())
            assert "rejected" in status.lower()
            assert API_KEY not in status
            assert has_model_key(secrets) is False

    asyncio.run(exercise())


def test_byok_panel_stores_valid_key_without_echoing_it() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Input

        secrets = FileSecretStore(Path("/tmp/pr-reviewer-byok-good"))
        stored: list[ModelKeyStored] = []

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ByokPanel(secrets=secrets, key_checker=lambda *_args: None)

            def on_model_key_stored(self, message: ModelKeyStored) -> None:
                stored.append(message)

        async with Harness().run_test() as pilot:
            
            field = pilot.app.query_one("#byok-key-input", Input)
            field.value = API_KEY
            await pilot.click("#byok-save")
            status = str(pilot.app.query_one("#byok-status").render())
            assert "saved" in status.lower()
            assert API_KEY not in status
            assert secrets.get(MODEL_KEY_SECRET) == API_KEY
            assert stored

    asyncio.run(exercise())


def test_connected_app_without_model_key_shows_byok_screen(tmp_path: Path) -> None:
    async def exercise() -> None:
        from pr_reviewer.tui.app import ReviewerApp
        from pr_reviewer.tui.installation_snapshot import InstallationSnapshot

        secrets = FileSecretStore(tmp_path)
        secrets.set("runner_credential", "test-runner-credential")
        snapshot = InstallationSnapshot(
            github_login="the-niresh",
            github_user_id=42,
            installation_id=7010,
            repositories=(),
        )
        app = ReviewerApp(secrets=secrets, installation_snapshot=snapshot)
        async with app.run_test():
            assert app.query_one("#model-access-screen", ModelAccessPanel) is not None

    asyncio.run(exercise())


def test_byok_panel_reports_provider_failures() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Input

        secrets = FileSecretStore(Path("/tmp/pr-reviewer-byok-fail"))

        def fail(_provider: str, _key: str) -> None:
            raise ModelProviderFailure()

        fail_checker: ModelKeyChecker = fail

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ByokPanel(secrets=secrets, key_checker=fail_checker)

        async with Harness().run_test() as pilot:
            
            field = pilot.app.query_one("#byok-key-input", Input)
            field.value = API_KEY
            await pilot.click("#byok-save")
            status = str(pilot.app.query_one("#byok-status").render())
            assert "could not verify" in status.lower()

    asyncio.run(exercise())
