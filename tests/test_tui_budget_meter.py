"""TUI step 2/3 (phase 30/32 reassignment): a live cost meter shows tokens spent and budget
remaining during a review. Unset stays a denial, never an unlimited-looking blank meter.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from pr_reviewer.local_store.budget import BudgetStatus
from pr_reviewer.tui.screens.review import ReviewPanel


def test_budget_meter_shows_spent_and_remaining() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        status = BudgetStatus(
            spent_tokens=400,
            spent_cost_usd=Decimal("0.40"),
            max_tokens=1000,
            max_cost_usd=Decimal("1.00"),
        )

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.set_budget_status(status)
            await pilot.pause()
            meter = pilot.app.query_one("#review-budget-meter")
            text = str(meter.render())
            assert "400/1000" in text
            assert "600" in text  # remaining tokens
            assert "0.40" in text
            assert "0.60" in text  # remaining cost

    asyncio.run(exercise())


def test_budget_meter_says_unset_plainly_rather_than_looking_free() -> None:
    async def exercise() -> None:
        from textual.app import App, ComposeResult

        class Harness(App[None]):
            def compose(self) -> ComposeResult:
                yield ReviewPanel(())

        async with Harness().run_test() as pilot:
            panel = pilot.app.query_one(ReviewPanel)
            panel.set_budget_status(None)
            await pilot.pause()
            meter = pilot.app.query_one("#review-budget-meter")
            text = str(meter.render())
            assert "not set" in text
            assert "0/0" not in text

    asyncio.run(exercise())
