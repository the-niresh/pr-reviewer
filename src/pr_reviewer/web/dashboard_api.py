"""Loopback dashboard API. Local and hosted I/O are injected."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pr_reviewer.observability.trace import reconstruct_trace
from pr_reviewer.web.local_auth import (
    LOOPBACK_UI_ORIGINS,
    client_is_loopback,
    csrf_is_valid,
    new_session_response,
    require_loopback_bind,
    session_is_valid,
)
from pr_reviewer.web.schemas import ApprovalBody, CostItem, FindingItem, JobItem


class DashboardJob(Protocol):
    job_id: str
    runner_id: str
    repository_id: int
    status: str


class DashboardFinding(Protocol):
    id: str
    review_job_id: str
    title: str
    status: str


class DashboardStore(Protocol):
    def list_jobs(self, **kwargs: Any) -> Sequence[DashboardJob]: ...
    def get_job(self, job_id: str) -> DashboardJob | None: ...
    def list_findings(self, job_id: str) -> Sequence[DashboardFinding]: ...
    def get_finding(self, finding_id: str) -> DashboardFinding | None: ...
    def list_events(self, job_id: str) -> Sequence[dict[str, Any]]: ...
    def job_costs(self, job_id: str) -> dict[str, Any] | None: ...
    def list_eval_reports(self) -> Sequence[dict[str, Any]]: ...
    def list_pending_approvals(self) -> Sequence[DashboardFinding]: ...
    def decide_approval(self, finding_id: str, decision: str) -> str: ...
    def connector_status(self) -> dict[str, str]: ...
    def fetch_local_trace(self, job_id: str) -> Any: ...


class HostedTraceLoader(Protocol):
    def fetch_hosted_trace(self, job_id: str) -> Any: ...


def create_dashboard_app(
    *,
    host: str,
    session_secret: str,
    runner_id: str,
    allowed_repository_ids: Sequence[int],
    store: DashboardStore,
    hosted_trace_loader: HostedTraceLoader,
) -> FastAPI:
    secret = require_loopback_bind(host, session_secret)
    allowed = frozenset(allowed_repository_ids)
    app = FastAPI(title="PR Reviewer local dashboard")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOOPBACK_UI_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-CSRF-Token", "Content-Type"],
    )

    def deny(status_code: int, error: str) -> JSONResponse:
        return JSONResponse({"error": error}, status_code=status_code)

    def visible_job(job_id: str) -> DashboardJob | None:
        job = store.get_job(job_id)
        if job is None:
            return None
        if job.runner_id != runner_id or job.repository_id not in allowed:
            return None
        return job

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Any:
        if not client_is_loopback(request):
            return deny(403, "loopback_only")
        path = request.url.path
        public = path in {"/dashboard/health", "/dashboard/session"} or request.method == "OPTIONS"
        if path.startswith("/dashboard/") and not public and not session_is_valid(secret, request):
            return deny(401, "unauthenticated")
        return await call_next(request)

    @app.get("/dashboard/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/dashboard/session")
    def session() -> JSONResponse:
        return new_session_response(secret)

    @app.get("/dashboard/account")
    def account() -> dict[str, str]:
        return {"runner_id": runner_id}

    @app.get("/dashboard/jobs")
    def list_jobs(after: str | None = None, limit: int = 50) -> dict[str, Any]:
        size = min(max(limit, 1), 100)
        jobs = [
            job
            for job in store.list_jobs()
            if job.runner_id == runner_id and job.repository_id in allowed
        ]
        jobs = sorted(jobs, key=lambda item: item.job_id)
        if after is not None:
            jobs = [job for job in jobs if job.job_id > after]
        items = [
            JobItem(
                job_id=job.job_id,
                runner_id=job.runner_id,
                repository_id=job.repository_id,
                status=job.status,
            ).model_dump()
            for job in jobs[:size]
        ]
        return {"items": items}

    @app.get("/dashboard/jobs/{job_id}", response_model=None)
    def get_job(job_id: str) -> JSONResponse | dict[str, Any]:
        job = visible_job(job_id)
        if job is None:
            return deny(404, "not_found")
        return JobItem(
            job_id=job.job_id,
            runner_id=job.runner_id,
            repository_id=job.repository_id,
            status=job.status,
        ).model_dump()

    @app.get("/dashboard/jobs/{job_id}/findings", response_model=None)
    def job_findings(job_id: str) -> JSONResponse | dict[str, Any]:
        if visible_job(job_id) is None:
            return deny(404, "not_found")
        items = [
            FindingItem(
                id=item.id,
                review_job_id=item.review_job_id,
                title=item.title,
                status=item.status,
            ).model_dump()
            for item in store.list_findings(job_id)
        ]
        return {"items": items}

    @app.get("/dashboard/jobs/{job_id}/events", response_model=None)
    def job_events(job_id: str) -> JSONResponse | dict[str, Any]:
        if visible_job(job_id) is None:
            return deny(404, "not_found")
        return {"items": [_redact(dict(item)) for item in store.list_events(job_id)]}

    @app.get("/dashboard/jobs/{job_id}/costs", response_model=None)
    def job_costs(job_id: str) -> JSONResponse | dict[str, Any]:
        if visible_job(job_id) is None:
            return deny(404, "not_found")
        raw = store.job_costs(job_id) or {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
        }
        return CostItem.model_validate(raw).model_dump()

    @app.get("/dashboard/jobs/{job_id}/trace", response_model=None)
    def job_trace(job_id: str) -> JSONResponse | dict[str, Any]:
        if visible_job(job_id) is None:
            return deny(404, "not_found")
        result = reconstruct_trace(
            job_id,
            hosted_trace_loader.fetch_hosted_trace(job_id),
            store.fetch_local_trace(job_id),
        )
        return {
            "job_id": result.job_id,
            "trace_id": result.trace_id,
            "segments": [
                {
                    "origin": segment.origin,
                    "trace_id": segment.trace_id,
                    "span_id": segment.span_id,
                    "parent_span_id": segment.parent_span_id,
                    "timestamp": segment.timestamp,
                    "kind": segment.kind,
                    "payload": dict(segment.payload),
                    "placement": segment.placement,
                }
                for segment in result.segments
            ],
            "missing_origins": sorted(result.missing_origins),
        }

    @app.get("/dashboard/evals")
    def evals() -> dict[str, Any]:
        return {"items": list(store.list_eval_reports())}

    @app.get("/dashboard/approvals")
    def approvals() -> dict[str, Any]:
        items = [
            FindingItem(
                id=item.id,
                review_job_id=item.review_job_id,
                title=item.title,
                status=item.status,
            ).model_dump()
            for item in store.list_pending_approvals()
        ]
        items = sorted(items, key=lambda item: item["id"])
        return {"items": items}

    @app.post("/dashboard/approvals/{finding_id}")
    def decide(
        finding_id: str,
        body: ApprovalBody,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        if not csrf_is_valid(secret, request, x_csrf_token):
            return deny(403, "csrf")
        result = store.decide_approval(finding_id, body.decision)
        if result == "conflict":
            return deny(409, "conflict")
        if result != "ok":
            return deny(404, "not_found")
        return JSONResponse({"status": "ok"})

    @app.get("/dashboard/connectors")
    def connectors() -> dict[str, str]:
        return store.connector_status()

    return app


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("token", "key", "secret", "password")):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact(inner)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
