"""Budget policy shared by both planes. Unset means deny, not unlimited.

Per-job reservation is executed by local_store.budget against runner SQLite.
Aggregate repository enforcement is executed by control_plane.budget against Neon.
The two stay consistent when the runner is offline mid-job because the hosted
reservation is keyed by job_id and stays held until the job is dead, cancelled,
or committed. Local reservation dies with the process; a recovered runner starts
a new local reservation against the job envelope, not against the repo cap.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

BudgetDeniedReason = Literal["unset", "insufficient"]


class BudgetDenied(Exception):
    def __init__(self, reason: BudgetDeniedReason) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class BudgetLimit:
    max_tokens: int | None
    max_cost_usd: Decimal | None


def is_configured(limit: BudgetLimit | None) -> bool:
    if limit is None:
        return False
    if limit.max_tokens is None or limit.max_cost_usd is None:
        return False
    return limit.max_tokens > 0 and limit.max_cost_usd > 0


def require_configured(limit: BudgetLimit | None) -> BudgetLimit:
    if not is_configured(limit):
        raise BudgetDenied("unset")
    assert limit is not None
    return limit
