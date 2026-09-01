"""Seeded Task 21 dashboard API for Playwright. Not a product entrypoint."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import uvicorn

from pr_reviewer.observability.trace import (
    HostedTrace,
    HostedTraceEvent,
    LocalTrace,
    LocalTraceEvent,
)
from pr_reviewer.web.dashboard_api import create_dashboard_app

JOB_ID = "job-dash-1"
EMPTY_JOB_ID = "job-empty-1"
FOREIGN_JOB_ID = "job-foreign-99"
RUNNER_ID = "runner-a"
FINDING_APPROVE = "f-dash-approve"
FINDING_REJECT = "f-dash-reject"
TITLE_APPROVE = "Null check on widget.value"
TITLE_REJECT = "Reject this queued finding"
CONTEXT_SNIPPET = "widget.py:14 retrieved from memory-v1"
EVAL_ID = "eval-holdout-blocked"


class MemoryJob:
    def __init__(
        self,
        job_id: str,
        *,
        runner_id: str = RUNNER_ID,
        repository_id: int = 11,
        status: str = "completed",
    ) -> None:
        self.job_id = job_id
        self.runner_id = runner_id
        self.repository_id = repository_id
        self.status = status


class MemoryFinding:
    def __init__(
        self,
        finding_id: str,
        job_id: str,
        *,
        status: str = "queued_for_human",
        title: str = TITLE_APPROVE,
    ) -> None:
        self.id = finding_id
        self.review_job_id = job_id
        self.status = status
        self.title = title


class MemoryStore:
    def __init__(self) -> None:
        self.jobs: dict[str, MemoryJob] = {}
        self.findings: dict[str, MemoryFinding] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.costs: dict[str, dict[str, Any]] = {}
        self.eval_reports: list[dict[str, Any]] = []
        self.local_traces: dict[str, Any] = {}
        self.connectors: dict[str, str] = {"github": "connected", "model": "ready"}

    def list_jobs(self, **_kwargs: Any) -> list[MemoryJob]:
        return [self.jobs[key] for key in sorted(self.jobs)]

    def get_job(self, job_id: str) -> MemoryJob | None:
        return self.jobs.get(job_id)

    def list_findings(self, job_id: str) -> list[MemoryFinding]:
        return [item for item in self.findings.values() if item.review_job_id == job_id]

    def get_finding(self, finding_id: str) -> MemoryFinding | None:
        return self.findings.get(finding_id)

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        return list(self.events.get(job_id, []))

    def job_costs(self, job_id: str) -> dict[str, Any] | None:
        return self.costs.get(job_id)

    def list_eval_reports(self) -> list[dict[str, Any]]:
        return list(self.eval_reports)

    def list_pending_approvals(self) -> list[MemoryFinding]:
        return [item for item in self.findings.values() if item.status == "queued_for_human"]

    def decide_approval(self, finding_id: str, decision: str) -> str:
        finding = self.findings.get(finding_id)
        if finding is None:
            return "not_found"
        if finding.status != "queued_for_human":
            return "conflict"
        finding.status = "approved" if decision == "approved" else "rejected"
        return "ok"

    def connector_status(self) -> dict[str, str]:
        return dict(self.connectors)

    def fetch_local_trace(self, job_id: str) -> Any:
        return self.local_traces.get(job_id)


class HostedLoader:
    def __init__(self) -> None:
        self.traces: dict[str, Any] = {}

    def fetch_hosted_trace(self, job_id: str) -> Any:
        return self.traces.get(job_id)


def seed_store() -> tuple[MemoryStore, HostedLoader]:
    store = MemoryStore()
    store.jobs[JOB_ID] = MemoryJob(JOB_ID)
    store.jobs[EMPTY_JOB_ID] = MemoryJob(EMPTY_JOB_ID, status="queued")
    store.jobs[FOREIGN_JOB_ID] = MemoryJob(FOREIGN_JOB_ID, repository_id=99)
    store.findings[FINDING_APPROVE] = MemoryFinding(FINDING_APPROVE, JOB_ID, title=TITLE_APPROVE)
    store.findings[FINDING_REJECT] = MemoryFinding(FINDING_REJECT, JOB_ID, title=TITLE_REJECT)
    store.events[JOB_ID] = [
        {
            "type": "retrieved_context",
            "snippet": CONTEXT_SNIPPET,
            "source": "memory-v1",
        }
    ]
    store.costs[JOB_ID] = {"input_tokens": 1200, "output_tokens": 80, "cost_usd": 0.42}
    store.eval_reports = [
        {
            "id": EVAL_ID,
            "blocked": True,
            "reason": "holdout is empty",
            "baseline": "single-pass",
            "candidate": "specialists",
        }
    ]
    store.local_traces[JOB_ID] = LocalTrace(
        trace_id="trace-dash-1",
        events=(
            LocalTraceEvent(
                sequence=1,
                kind="workflow.step_completed",
                payload={"step": "fetch"},
                created_at="2026-09-01T00:00:00Z",
            ),
        ),
    )
    hosted = HostedLoader()
    hosted.traces[JOB_ID] = HostedTrace(
        trace_id="trace-dash-1",
        events=(
            HostedTraceEvent(
                sequence=1,
                kind="review_job_acknowledged",
                payload={"job_id": JOB_ID},
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
        ),
    )
    return store, hosted


def main() -> None:
    store, hosted = seed_store()
    app = create_dashboard_app(
        host="127.0.0.1",
        session_secret="playwright-dashboard-session",
        runner_id=RUNNER_ID,
        allowed_repository_ids=(11, 22),
        store=store,
        hosted_trace_loader=hosted,
    )
    uvicorn.run(app, host="127.0.0.1", port=8742, log_level="warning")


if __name__ == "__main__":
    main()
