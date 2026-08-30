"""Failing tests for the GitHub connector wrap (master Task 8).

Wraps the existing token-mint and PR-fetch calls without changing their public
signatures. Records timeout, error class, status code, latency, payload size, and
an allowlisted audit row. Imports of connectors.github stay inside test bodies.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pr_reviewer.contracts import PullRequestRef
from pr_reviewer.db.client import connection
from pr_reviewer.github.app_client import GitHubAppClient
from pr_reviewer.github.pull_request import fetch_pull_request
from pr_reviewer.github.tokens import GitHubAppSettings
from pr_reviewer.jobs import enqueue_review_job

_GITHUB_TOKEN_PREFIXES = ("gho_", "ghu_", "ghs_", "github_pat_")


def _settings() -> GitHubAppSettings:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return GitHubAppSettings(app_id="123", private_key=private_key)


def _job_with_trace() -> tuple[str, str]:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (8302, "acme"),
        )
    payload = {
        "action": "opened",
        "installation": {"id": 8302},
        "repository": {"id": 93002, "name": "widgets"},
        "pull_request": {
            "number": 5,
            "base": {"sha": "a" * 40},
            "head": {"sha": "b" * 40},
        },
    }
    assert enqueue_review_job("delivery-connector-gh-1", "pull_request", payload) == "enqueued"
    with connection() as conn:
        row = conn.execute(
            "select id, trace_id from review_jobs where delivery_id = %s",
            ("delivery-connector-gh-1",),
        ).fetchone()
    assert row is not None
    assert row["trace_id"] is not None
    return str(row["id"]), str(row["trace_id"])


def test_wrapping_does_not_change_existing_github_public_signatures() -> None:
    token_params = inspect.signature(GitHubAppClient.create_installation_token).parameters
    assert "installation_id" in token_params
    assert "repository_ids" in token_params
    assert "permissions" in token_params
    fetch_params = inspect.signature(fetch_pull_request).parameters
    assert "ref" in fetch_params
    assert "installation_id" in fetch_params
    assert "token_provider" in fetch_params


def test_wrapped_token_mint_records_status_latency_and_no_token() -> None:
    from pr_reviewer.connectors.audit import record_connector_run
    from pr_reviewer.connectors.github import create_installation_token

    job_id, trace_id = _job_with_trace()

    class FakeClient:
        def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout: float,
            json: dict[str, object] | None = None,
        ) -> httpx.Response:
            del timeout, json
            assert "gho_" not in headers.get("authorization", "").lower()
            return httpx.Response(
                201,
                request=httpx.Request("POST", url),
                json={
                    "token": "ghs_must_never_be_audited",
                    "expires_at": datetime(2030, 1, 1, tzinfo=UTC).isoformat(),
                },
            )

    client = GitHubAppClient(settings=_settings(), client=FakeClient())
    result = create_installation_token(
        client,
        99,
        repository_ids=[93002],
        permissions={"contents": "read", "pull_requests": "read"},
        trace_id=uuid.UUID(trace_id),
        review_job_id=job_id,
        record=record_connector_run,
    )
    assert result.connector == "github"
    assert result.operation == "create_installation_token"
    assert result.outcome == "success"
    assert result.status_code == 201
    assert result.latency_ms >= 0
    assert result.request_bytes >= 0
    assert result.response_bytes > 0
    assert result.value.token == "ghs_must_never_be_audited"  # type: ignore[union-attr]
    with connection() as conn:
        row = conn.execute(
            "select * from connector_runs where trace_id = %s",
            (trace_id,),
        ).fetchone()
    assert row is not None
    blob = " ".join(str(value) for value in dict(row).values())
    for prefix in _GITHUB_TOKEN_PREFIXES:
        assert prefix not in blob.lower()


def test_wrapped_fetch_records_timeout_as_an_error_class_not_a_body() -> None:
    from pr_reviewer.connectors.github import fetch_pull_request as wrapped_fetch

    class TimeoutClient:
        def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout: float,
        ) -> httpx.Response:
            del url, headers, timeout
            raise httpx.TimeoutException("github timed out")

    class TokenProvider:
        def create_installation_token(self, installation_id: int) -> str:
            assert installation_id == 99
            return "installation-token"

    result = wrapped_fetch(
        PullRequestRef(owner="acme", repository="widgets", number=5),
        installation_id=99,
        token_provider=TokenProvider(),
        client=TimeoutClient(),
        api_base_url="https://api.example.test",
        timeout_seconds=0.01,
        trace_id=uuid.uuid4(),
    )
    assert result.outcome == "error"
    assert result.error_kind == "timeout"
    assert result.value is None
    assert result.latency_ms >= 0


def test_wrapped_fetch_records_http_status_and_payload_size() -> None:
    from pr_reviewer.connectors.github import fetch_pull_request as wrapped_fetch

    class FakeClient:
        def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout: float,
        ) -> httpx.Response:
            del timeout
            assert headers["authorization"] == "Bearer installation-token"
            if url.endswith("/pulls/5"):
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json={
                        "base": {"sha": "base-sha"},
                        "head": {"sha": "head-sha"},
                        "title": "Add widget",
                        "body": None,
                    },
                )
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json=[
                    {
                        "filename": "src/one.py",
                        "status": "modified",
                        "patch": "@@ one",
                    }
                ],
            )

    class TokenProvider:
        def create_installation_token(self, installation_id: int) -> str:
            del installation_id
            return "installation-token"

    result = wrapped_fetch(
        PullRequestRef(owner="acme", repository="widgets", number=5),
        installation_id=99,
        token_provider=TokenProvider(),
        client=FakeClient(),
        api_base_url="https://api.example.test",
    )
    assert result.outcome == "success"
    assert result.status_code == 200
    assert result.error_kind is None
    assert result.latency_ms >= 0
    assert result.response_bytes > 0
    assert result.value is not None
    assert result.value.files[0].path == "src/one.py"


def test_wrapped_fetch_records_github_http_error_class() -> None:
    from pr_reviewer.connectors.github import fetch_pull_request as wrapped_fetch

    class FakeClient:
        def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout: float,
        ) -> httpx.Response:
            del headers, timeout
            return httpx.Response(502, request=httpx.Request("GET", url), json={"message": "bad"})

    class TokenProvider:
        def create_installation_token(self, installation_id: int) -> str:
            del installation_id
            return "installation-token"

    result = wrapped_fetch(
        PullRequestRef(owner="acme", repository="widgets", number=5),
        installation_id=99,
        token_provider=TokenProvider(),
        client=FakeClient(),
        api_base_url="https://api.example.test",
    )
    assert result.outcome == "error"
    assert result.error_kind == "http_error"
    assert result.status_code == 502
    assert result.value is None
