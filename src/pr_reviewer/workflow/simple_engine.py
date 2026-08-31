"""Plain-Python WorkflowEngine. Steps are injected; nothing here talks to Neon."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from pr_reviewer.contracts.runner import JobAcknowledgement, JobEnvelope, LeaseState
from pr_reviewer.workflow.engine import STEP_NAMES, WorkflowInput, WorkflowResult, WorkflowState
from pr_reviewer.workflow.store import WorkflowStore

StepHandler = Callable[[WorkflowInput, dict[str, object]], object]
HeartbeatFn = Callable[[WorkflowInput], LeaseState]
HeadShaFn = Callable[[WorkflowInput], str]
RecordEventFn = Callable[[str, str, dict[str, str | int]], None]


def wait_for_artifact(path: Path, *, deadline_seconds: float) -> None:
    deadline = time.monotonic() + deadline_seconds
    while True:
        if path.exists():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"TIMEOUT waiting for artifact {path}")
        time.sleep(min(0.01, remaining))


class SimpleEngine:
    def __init__(
        self,
        *,
        store: WorkflowStore,
        fetch: StepHandler,
        baseline_review: StepHandler,
        retrieval: StepHandler,
        verification: StepHandler,
        routing: StepHandler,
        storage: StepHandler,
        heartbeat: HeartbeatFn | None = None,
        current_head_sha: HeadShaFn | None = None,
        record_event: RecordEventFn | None = None,
        step_timeouts: dict[str, float] | None = None,
    ) -> None:
        self._store = store
        self._handlers: dict[str, StepHandler] = {
            "fetch": fetch,
            "baseline_review": baseline_review,
            "retrieval": retrieval,
            "verification": verification,
            "routing": routing,
            "storage": storage,
        }
        self._heartbeat = heartbeat
        self._current_head_sha = current_head_sha
        self._record_event = record_event
        self._step_timeouts = step_timeouts or {}

    def run(self, workflow_id: str, input: WorkflowInput) -> WorkflowResult:
        self._store.ensure_run(workflow_id, input)
        return self._advance(workflow_id, input)

    def resume(self, workflow_id: str) -> WorkflowResult:
        return self._advance(workflow_id, self._store.load_input(workflow_id))

    def get_state(self, workflow_id: str) -> WorkflowState:
        return self._store.get_state(workflow_id)

    def review(self, job: JobEnvelope) -> JobAcknowledgement:
        inp = WorkflowInput(
            job_id=str(job.job_id),
            head_sha=job.head_sha,
            trace_id=str(job.trace_id),
            lease_token=job.lease_token,
        )
        result = self.run(str(job.job_id), inp)
        digest = hashlib.sha256(f"{result.status}:{result.reason}".encode()).hexdigest()
        if result.status == "completed":
            return JobAcknowledgement(
                terminal_state="succeeded",
                error_class=None,
                input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal("0"),
                latency_ms=0,
                local_result_hash=digest,
            )
        return JobAcknowledgement(
            terminal_state="failed",
            error_class=result.reason,
            input_tokens=0,
            output_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=0,
            local_result_hash=digest,
        )

    def _advance(self, workflow_id: str, inp: WorkflowInput) -> WorkflowResult:
        state = self._store.get_state(workflow_id)
        if state.outcome == "completed":
            return WorkflowResult(status="completed", reason=state.reason)
        if state.outcome == "cancelled":
            return WorkflowResult(status="cancelled", reason=state.reason)
        if state.outcome == "failed":
            return WorkflowResult(status="failed", reason=state.reason)

        outputs = dict(self._store.completed_outputs(workflow_id))
        for name in STEP_NAMES:
            if name in outputs:
                continue
            stopped = self._checkpoint(inp, name)
            if stopped is not None:
                self._store.set_outcome(workflow_id, stopped.status, stopped.reason)
                return stopped
            started = time.monotonic()
            output = self._handlers[name](inp, outputs)
            timeout = self._step_timeouts.get(name)
            if timeout is not None and time.monotonic() - started > timeout:
                raise RuntimeError(f"TIMEOUT waiting for step {name}")
            self._store.mark_step_completed(workflow_id, name, output)
            outputs[name] = output
            self._emit(inp.job_id, "workflow.step_completed", {"step": name})

        self._store.set_outcome(workflow_id, "completed", None)
        return WorkflowResult(status="completed")

    def _checkpoint(self, inp: WorkflowInput, step_name: str) -> WorkflowResult | None:
        del step_name
        if self._heartbeat is not None:
            lease = self._heartbeat(inp)
            if lease.status == "cancelled":
                self._emit(inp.job_id, "workflow.cancelled", {"reason": "cancelled"})
                return WorkflowResult(status="cancelled", reason="cancelled")
            if lease.status == "invalid_or_expired":
                self._emit(
                    inp.job_id, "workflow.failed", {"reason": "invalid_or_expired"}
                )
                return WorkflowResult(status="failed", reason="invalid_or_expired")
        if self._current_head_sha is not None:
            live = self._current_head_sha(inp)
            if live != inp.head_sha:
                self._emit(inp.job_id, "workflow.cancelled", {"reason": "superseded"})
                return WorkflowResult(status="cancelled", reason="superseded")
        return None

    def _emit(self, job_id: str, event_type: str, payload: dict[str, str | int]) -> None:
        if self._record_event is not None:
            self._record_event(job_id, event_type, payload)
