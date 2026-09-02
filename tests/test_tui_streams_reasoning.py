"""Reasoning streams as it is produced."""

from __future__ import annotations

import asyncio

from pr_reviewer.tui.screens.review import AgentReasoningChunk, ReviewPanel


def test_reasoning_arrives_incrementally_not_in_one_block() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Button

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(
                    (),
                    reasoning_feed=(
                        AgentReasoningChunk("security", "first"),
                        AgentReasoningChunk("correctness", "second"),
                    ),
                    reasoning_stream_interval=0.2,
                )

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.on_button_pressed(
                Button.Pressed(panel.query_one("#review-continue", Button))
            )
            assert not panel.streamed_concerns
            await pilot.pause(delay=0.25)
            assert list(panel.streamed_concerns) == ["security"]
            await pilot.pause(delay=0.25)
            assert list(panel.streamed_concerns) == ["security", "correctness"]

    asyncio.run(exercise())
