"""Failing tests for the loopback dashboard API (master Task 21).

Local state is injected. The merged trace must come from reconstruct_trace.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

LOOPBACK_CLIENT = ("127.0.0.1", 50000)


class MemoryJob:
    def __init__(
        self,
        job_id: str,
        *,
        runner_id: str = "runner-a",
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
        title: str = "Null check",
    ) -> None:
        self.id = finding_id
        self.review_job_id = job_id
        self.status = status
        self.title = title
        self.rationale = "widget.value can be None."


class MemoryStore:
    def __init__(self) -> None:
        self.jobs: dict[str, MemoryJob] = {}
        self.findings: dict[str, MemoryFinding] = {}
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.costs: dict[str, dict[str, Any]] = {}
        self.eval_reports: list[dict[str, Any]] = []
        self.approval_calls: list[tuple[str, str]] = []
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
        self.approval_calls.append((finding_id, decision))
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


def _app(
    store: MemoryStore | None = None,
    hosted: HostedLoader | None = None,
    **overrides: Any,
) -> Any:
    from pr_reviewer.web.dashboard_api import create_dashboard_app

    fields: dict[str, Any] = {
        "host": "127.0.0.1",
        "session_secret": "dashboard-session-secret",
        "runner_id": "runner-a",
        "allowed_repository_ids": (11, 22),
        "store": store if store is not None else MemoryStore(),
        "hosted_trace_loader": hosted if hosted is not None else HostedLoader(),
    }
    fields.update(overrides)
    return create_dashboard_app(**fields)


def _client(app: Any) -> TestClient:
    return TestClient(app, client=LOOPBACK_CLIENT)


def _authed(store: MemoryStore | None = None, hosted: HostedLoader | None = None) -> TestClient:
    client = _client(_app(store, hosted))
    response = client.get("/dashboard/session")
    assert response.status_code == 200
    return client


def test_health_is_public_on_loopback() -> None:
    client = _client(_app())
    response = client.get("/dashboard/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_jobs_are_stable_ordered_and_paginated() -> None:
    store = MemoryStore()
    store.jobs["job-b"] = MemoryJob("job-b")
    store.jobs["job-a"] = MemoryJob("job-a")
    store.jobs["job-c"] = MemoryJob("job-c")
    client = _authed(store)
    first = client.get("/dashboard/jobs", params={"limit": 2})
    assert first.status_code == 200
    ids = [item["job_id"] for item in first.json()["items"]]
    assert ids == ["job-a", "job-b"]
    second = client.get("/dashboard/jobs", params={"after": "job-b", "limit": 2})
    assert [item["job_id"] for item in second.json()["items"]] == ["job-c"]


def test_missing_job_is_not_found() -> None:
    client = _authed()
    response = client.get("/dashboard/jobs/missing")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_findings_and_redacted_events_and_costs() -> None:
    store = MemoryStore()
    store.jobs["job-1"] = MemoryJob("job-1")
    store.findings["f-1"] = MemoryFinding("f-1", "job-1")
    store.events["job-1"] = [{"type": "model_call", "token": "sk-secret-value", "step": "review"}]
    store.costs["job-1"] = {"input_tokens": 10, "output_tokens": 4, "cost_usd": 0.02}
    client = _authed(store)
    findings = client.get("/dashboard/jobs/job-1/findings")
    assert findings.status_code == 200
    assert findings.json()["items"][0]["id"] == "f-1"
    events = client.get("/dashboard/jobs/job-1/events")
    assert events.status_code == 200
    payload = events.json()["items"][0]
    assert "sk-secret-value" not in str(payload)
    costs = client.get("/dashboard/jobs/job-1/costs")
    assert costs.status_code == 200
    assert costs.json()["cost_usd"] == 0.02


def test_evals_and_connectors() -> None:
    store = MemoryStore()
    store.eval_reports = [{"id": "eval-1", "blocked": True, "reason": "holdout is empty"}]
    client = _authed(store)
    evals = client.get("/dashboard/evals")
    assert evals.status_code == 200
    assert evals.json()["items"][0]["blocked"] is True
    connectors = client.get("/dashboard/connectors")
    assert connectors.status_code == 200
    assert connectors.json()["github"] == "connected"


def test_approval_race_returns_conflict() -> None:
    store = MemoryStore()
    store.jobs["job-1"] = MemoryJob("job-1")
    store.findings["f-1"] = MemoryFinding("f-1", "job-1")
    client = _authed(store)
    csrf = client.get("/dashboard/session").json()["csrf_token"]
    first = client.post(
        "/dashboard/approvals/f-1",
        json={"decision": "approved"},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 200
    second = client.post(
        "/dashboard/approvals/f-1",
        json={"decision": "approved"},
        headers={"X-CSRF-Token": csrf},
    )
    assert second.status_code == 409
    assert second.json()["error"] == "conflict"


def test_pending_approvals_list() -> None:
    store = MemoryStore()
    store.findings["f-1"] = MemoryFinding("f-1", "job-1")
    store.findings["f-2"] = MemoryFinding("f-2", "job-1", status="approved")
    client = _authed(store)
    response = client.get("/dashboard/approvals")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == ["f-1"]


def test_trace_merges_hosted_and_local_halves() -> None:
    from pr_reviewer.observability.trace import (
        HostedTrace,
        HostedTraceEvent,
        LocalTrace,
        LocalTraceEvent,
    )

    store = MemoryStore()
    store.jobs["job-1"] = MemoryJob("job-1")
    store.local_traces["job-1"] = LocalTrace(
        trace_id="trace-1",
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
    hosted.traces["job-1"] = HostedTrace(
        trace_id="trace-1",
        events=(
            HostedTraceEvent(
                sequence=1,
                kind="review_job_acknowledged",
                payload={"job_id": "job-1"},
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
            ),
        ),
    )
    client = _authed(store, hosted)
    response = client.get("/dashboard/jobs/job-1/trace")
    assert response.status_code == 200
    body = response.json()
    origins = {item["origin"] for item in body["segments"]}
    assert origins == {"hosted", "local"}
    assert body["missing_origins"] == []
