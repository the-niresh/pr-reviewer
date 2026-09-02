"""Model keys must never leave this machine on outbound HTTP."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from pr_reviewer.runner.secrets import FileSecretStore

API_KEY = "sk-never-leave-the-machine-key"


def test_model_key_is_not_sent_to_the_hosted_plane() -> None:
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)

    async def exercise() -> None:
        from textual.app import App, ComposeResult

        from pr_reviewer.tui.screens.model_access import ModelAccessPanel

        secrets = FileSecretStore(Path("/tmp/pr-reviewer-never-leaves"))

        def checker(provider_id: str, api_key: str) -> None:
            from pr_reviewer.models.provider import verify_provider_api_key

            with httpx.Client(
                transport=transport,
                base_url="https://api.openai.com",
            ) as client:
                verify_provider_api_key(provider_id, api_key, http=client)

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ModelAccessPanel(secrets=secrets, key_checker=checker)

        async with Harness().run_test() as pilot:
            pilot.app.query_one("#model-access-key-input").value = API_KEY
            await pilot.click("#model-access-save")

        for request in recorded:
            host = str(request.url.host or "")
            if host.endswith("openai.com") or host.endswith("anthropic.com"):
                continue
            blob = f"{request.url} {request.headers} {request.content!r}"
            assert API_KEY not in blob

    asyncio.run(exercise())
