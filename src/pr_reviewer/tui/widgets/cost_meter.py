"""Live cost meter: tokens spent and budget remaining during a review.

A separate widget, not inline text in the review screen, so it composes into other screens
(the evals section, per the orchestrator) and is testable in isolation.
"""

from __future__ import annotations

from textual.widgets import Label

from pr_reviewer.local_store.budget import BudgetStatus


class CostMeter(Label):
    """None means unset, which is a deny (reliability/budget.py), never an unlimited meter --
    the unset state is rendered plainly, not as a blank or a zero that could read as free.
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__("", id=id)

    def update_status(self, status: BudgetStatus | None) -> None:
        if status is None:
            self.update("Budget: not set (reviews without a budget do not run)")
            return
        self.update(
            f"Budget: {status.spent_tokens}/{status.max_tokens} tokens, "
            f"${status.spent_cost_usd} of ${status.max_cost_usd} spent "
            f"({status.remaining_tokens} tokens, ${status.remaining_cost_usd} remaining)"
        )
