"""WorkflowEngine interface (ADR-003). Implementations live beside this file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

WorkflowStatus = Literal["completed", "cancelled", "failed"]

STEP_NAMES = (
    "fetch",
    "baseline_review",
    "retrieval",
    "verification",
    "routing",
    "storage",
)


@dataclass(frozen=True)
class WorkflowInput:
    job_id: str
    head_sha: str
    trace_id: str
    lease_token: str = ""


@dataclass(frozen=True)
class WorkflowResult:
    status: WorkflowStatus
    reason: str | None = None


@dataclass(frozen=True)
class WorkflowState:
    workflow_id: str
    completed_steps: tuple[str, ...]
    outcome: str | None
    reason: str | None = None


class WorkflowEngine(Protocol):
    def run(self, workflow_id: str, input: WorkflowInput) -> WorkflowResult: ...
    def resume(self, workflow_id: str) -> WorkflowResult: ...
    def get_state(self, workflow_id: str) -> WorkflowState: ...
