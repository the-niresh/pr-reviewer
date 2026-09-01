"""Per-agent reasoning streams live in the review screen."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pr_reviewer.local_store.review_log import ReviewLogStore
from pr_reviewer.reviewer.specialists import SPECIALIST_CONCERNS
from pr_reviewer.tui.screens.review import AgentReasoningChunk, ReviewPanel


def test_agent_reasoning_streams_after_diffs_phase(tmp_path: Path) -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult
        from textual.widgets import Button

        log = ReviewLogStore(tmp_path / "review_log.json")
        feed = tuple(
            AgentReasoningChunk(concern, f"{concern} stream")
            for concern in SPECIALIST_CONCERNS
        )

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(
                    (),
                    review_log=log,
                    review_id="review-1",
                    reasoning_feed=feed,
                    stream_immediately=True,
                )

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            assert panel.phase == "diffs"
            panel.on_button_pressed(
                Button.Pressed(panel.query_one("#review-continue", Button))
            )
            assert panel.phase == "agents"
            assert panel.streamed_concerns == SPECIALIST_CONCERNS
            for index, concern in enumerate(SPECIALIST_CONCERNS, start=1):
                assert pilot.app.query_one(f"#reasoning-{concern}-{index}") is not None
            records = log.list_reasoning("review-1")
            assert [record.concern for record in records] == list(SPECIALIST_CONCERNS)

    asyncio.run(exercise())


def test_reasoning_is_not_shown_before_diffs_are_acknowledged() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel((), stream_immediately=True)

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            assert panel.agents_visible is False
            assert panel.streamed_concerns == ()

    asyncio.run(exercise())
