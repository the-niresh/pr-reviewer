"""The TUI tells the user plainly when tokens run out."""

from __future__ import annotations

import asyncio

from pr_reviewer.tui.out_of_tokens import OutOfTokensState
from pr_reviewer.tui.screens.review import ReviewPanel


def test_out_of_tokens_message_is_rendered_in_plain_words() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Button

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel((), stream_immediately=True)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.on_button_pressed(
                Button.Pressed(panel.query_one("#review-continue", Button))
            )
            # The reason carries a JSON-shaped provider payload on purpose: this is the
            # exact string that must never reach the screen. If show_out_of_tokens ever
            # started rendering state.reason instead of the plain-words message, this test
            # would fail on the "{" assertion below.
            panel.show_out_of_tokens(
                OutOfTokensState(
                    provider="openai",
                    reason='insufficient_quota: {"code": "billing_hard_limit_reached"}',
                )
            )
            rendered = str(pilot.app.query_one("#review-out-of-tokens").render())
            assert "OpenAI balance is exhausted" in rendered
            assert "Add credits or switch provider" in rendered
            assert "Traceback" not in rendered
            assert "{" not in rendered

    asyncio.run(exercise())
