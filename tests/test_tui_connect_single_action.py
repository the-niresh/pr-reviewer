"""Connect screen offers exactly one action: sign in."""

from __future__ import annotations

import asyncio

from pr_reviewer.tui.screens.connect import ConnectConfig, ConnectPanel


class FakePairingClient:
    def create_code(self, device_name: str, challenge: str) -> str:
        return "PAIR-SINGLE-1"

    def status(self, code: str, challenge: str) -> str:
        return "pending"


def test_connect_screen_offers_only_sign_in() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Button

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ConnectPanel(
                    config=ConnectConfig(
                        hosted_origin="https://reviewer.niresh.tech",
                        device_name="test-laptop",
                    ),
                    pairing_client=FakePairingClient(),
                )

        async with Harness().run_test() as pilot:
            buttons = pilot.app.query(Button)
            assert len(buttons) == 1
            assert "sign in" in str(buttons[0].render()).lower()
            assert len(pilot.app.query("#install-url")) == 0
            assert len(pilot.app.query("#sign-in-url")) == 0
            assert len(pilot.app.query("#pairing-code")) == 0

    asyncio.run(exercise())
