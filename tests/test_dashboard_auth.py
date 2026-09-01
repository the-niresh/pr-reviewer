"""Failing tests for loopback dashboard auth (master Task 21).

Denials matter more than successes. web/ stays hosted-side in the guard, so the
dashboard modules must not import runner-side packages. Imports of new modules
stay inside test bodies.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
LOOPBACK_CLIENT = ("127.0.0.1", 50000)
REMOTE_CLIENT = ("8.8.8.8", 50000)


def _app(**overrides: Any) -> Any:
    from pr_reviewer.web.dashboard_api import create_dashboard_app

    fields: dict[str, Any] = {
        "host": "127.0.0.1",
        "session_secret": "dashboard-session-secret",
        "runner_id": "runner-a",
        "allowed_repository_ids": (11, 22),
        "store": _EmptyStore(),
        "hosted_trace_loader": _EmptyHosted(),
    }
    fields.update(overrides)
    return create_dashboard_app(**fields)


class _ForeignJob:
    def __init__(self, job_id: str, runner_id: str, repository_id: int) -> None:
        self.job_id = job_id
        self.runner_id = runner_id
        self.repository_id = repository_id
        self.status = "completed"


class _EmptyStore:
    def list_jobs(self, **_kwargs: Any) -> list[Any]:
        return []

    def get_job(self, job_id: str) -> Any:
        if job_id == "job-other-runner":
            return _ForeignJob(job_id, "runner-b", 11)
        if job_id == "job-other-repo":
            return _ForeignJob(job_id, "runner-a", 99)
        return None

    def list_findings(self, job_id: str) -> list[Any]:
        del job_id
        return []

    def get_finding(self, finding_id: str) -> Any:
        del finding_id
        return None

    def list_events(self, job_id: str) -> list[Any]:
        del job_id
        return []

    def job_costs(self, job_id: str) -> Any:
        del job_id
        return None

    def list_eval_reports(self) -> list[Any]:
        return []

    def list_pending_approvals(self) -> list[Any]:
        return []

    def decide_approval(self, finding_id: str, decision: str) -> str:
        del finding_id, decision
        return "not_found"

    def connector_status(self) -> Any:
        return {"github": "disconnected", "model": "missing"}

    def fetch_local_trace(self, job_id: str) -> Any:
        del job_id
        return None


class _EmptyHosted:
    def fetch_hosted_trace(self, job_id: str) -> Any:
        del job_id
        return None


def _client(app: Any, *, client: tuple[str, int] = LOOPBACK_CLIENT) -> TestClient:
    return TestClient(app, client=client)


def _session(client: TestClient) -> str:
    response = client.get("/dashboard/session")
    assert response.status_code == 200
    token = response.json()["csrf_token"]
    assert token
    return str(token)


def test_non_loopback_bind_is_rejected() -> None:
    from pr_reviewer.web.local_auth import DashboardBindError

    for host in ("0.0.0.0", "192.168.1.10", "::"):
        with pytest.raises(DashboardBindError):
            _app(host=host)


def test_missing_session_secret_is_rejected() -> None:
    from pr_reviewer.web.local_auth import DashboardBindError

    with pytest.raises(DashboardBindError):
        _app(session_secret="")


def test_non_loopback_client_is_denied() -> None:
    client = _client(_app(), client=REMOTE_CLIENT)
    response = client.get("/dashboard/jobs")
    assert response.status_code == 403
    assert response.json()["error"] == "loopback_only"


def test_unauthenticated_request_is_denied() -> None:
    client = _client(_app())
    response = client.get("/dashboard/jobs")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_session_cookie_flags_are_strict() -> None:
    client = _client(_app())
    response = client.get("/dashboard/session")
    cookie = response.cookies.get("pr_reviewer_dashboard_session")
    assert cookie
    header = response.headers.get("set-cookie", "").lower()
    assert "httponly" in header
    assert "samesite=strict" in header


def test_write_without_csrf_is_denied() -> None:
    client = _client(_app())
    _session(client)
    response = client.post("/dashboard/approvals/finding-1", json={"decision": "approved"})
    assert response.status_code == 403
    assert response.json()["error"] == "csrf"


def test_loopback_ui_origin_is_allowed_for_cors() -> None:
    client = _client(_app())
    origin = "http://127.0.0.1:3000"
    response = client.options(
        "/dashboard/jobs",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == origin


def test_non_loopback_origin_is_not_granted_cors() -> None:
    client = _client(_app())
    response = client.options(
        "/dashboard/jobs",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"


def test_wrong_runner_scope_is_indistinguishable_from_not_found() -> None:
    client = _client(_app(runner_id="runner-a"))
    _session(client)
    response = client.get("/dashboard/jobs/job-other-runner")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_wrong_repository_scope_is_indistinguishable_from_not_found() -> None:
    client = _client(_app(allowed_repository_ids=(11,)))
    _session(client)
    response = client.get("/dashboard/jobs/job-other-repo")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_account_uses_paired_runner_identity_not_the_local_session() -> None:
    client = _client(_app(runner_id="paired-runner-9"))
    _session(client)
    response = client.get("/dashboard/account")
    assert response.status_code == 200
    body = response.json()
    assert body["runner_id"] == "paired-runner-9"
    assert "pr_reviewer_dashboard_session" not in str(body)


def test_dashboard_modules_do_not_import_runner_or_hosted_handles() -> None:
    forbidden = (
        "pr_reviewer.local_store",
        "pr_reviewer.runner",
        "pr_reviewer.control_plane",
        "pr_reviewer.db",
        "pr_reviewer.cli",
    )
    for name in ("local_auth.py", "dashboard_api.py", "schemas.py"):
        path = SRC_ROOT / "web" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(item) for item in forbidden)


def test_web_package_init_does_not_import_the_hosted_app() -> None:
    source = (SRC_ROOT / "web" / "__init__.py").read_text(encoding="utf-8")
    assert "control_plane" not in source
    assert "web.app" not in source


def test_dashboard_exposes_no_webhook_route() -> None:
    app = _app()
    paths = [getattr(route, "path", "") for route in app.routes]
    assert all("webhook" not in path for path in paths)
    client = _client(app)
    assert client.post("/webhook").status_code == 404
