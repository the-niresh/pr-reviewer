"""TUI step 3/3 (phase 32 reassignment): a first-class panel for what the review could not
determine -- every omitted file with its real reason, never hidden, never silently empty.
"""

from __future__ import annotations

import asyncio

from pr_reviewer.contracts.github import OmissionReason
from pr_reviewer.contracts.review_context import OmittedFile, PackedDiff
from pr_reviewer.tui.screens.review import ReviewPanel


def _packed(omitted_files: tuple[OmittedFile, ...]) -> PackedDiff:
    return PackedDiff(
        packing_strategy_version="v1",
        items=(),
        included_files=(),
        omitted_files=omitted_files,
        prompt_tokens=0,
        covers_all_changed_files=not omitted_files,
    )


def test_omitted_files_are_shown_with_their_real_reason() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        packed = _packed(
            (
                OmittedFile(
                    path="huge_file.py",
                    reason=OmissionReason.TOKEN_BUDGET,
                    change_size=50_000,
                ),
            )
        )

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.set_undetermined(packed)
            await pilot.pause()
            item = pilot.app.query_one("#undetermined-huge_file_py")
            text = str(item.render())
            assert "huge_file.py" in text
            assert "token_budget" in text
            assert "50000" in text

    asyncio.run(exercise())


def test_full_coverage_says_so_rather_than_leaving_the_panel_empty() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.set_undetermined(_packed(()))
            await pilot.pause()
            container = pilot.app.query_one("#review-undetermined-panel")
            text = " ".join(str(child.render()) for child in container.query("*"))
            assert "Full coverage" in text

    asyncio.run(exercise())
