from __future__ import annotations

import hmac
import json
from hashlib import sha256
from typing import Any

from fastapi.testclient import TestClient

from pr_reviewer.db.client import connection
from pr_reviewer.web.app import app

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
INSTALLATION_ID = 8401
REPOSITORY_ID = 94001


def signature(body: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()


def _pull_request_payload(
    *,
    action: str,
    draft: bool = False,
    number: int = 7,
    installation_id: int = INSTALLATION_ID,
    repository_id: int = REPOSITORY_ID,
) -> dict[str, Any]:
    return {
        "action": action,
        "installation": {"id": installation_id},
        "repository": {
            "id": repository_id,
            "name": "widgets",
            "owner": {"login": "acme"},
        },
        "pull_request": {
            "number": number,
            "draft": draft,
            "base": {"sha": BASE_SHA},
            "head": {"sha": HEAD_SHA},
        },
    }


def _post_webhook(
    client: TestClient,
    delivery_id: str,
    payload: dict[str, Any],
    *,
    event: str = "pull_request",
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/api/github/webhook",
        content=body,
        headers={
            "x-github-delivery": delivery_id,
            "x-github-event": event,
            "x-hub-signature-256": signature(body),
        },
    )


def _insert_installation(installation_id: int = INSTALLATION_ID) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (installation_id, "acme"),
        )


def test_webhook_rejects_missing_headers_before_signature() -> None:
    client = TestClient(app)
    response = client.post("/api/github/webhook", content=b"{}")

    assert response.status_code == 400


def test_webhook_rejects_invalid_signature() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/github/webhook",
        content=b"{}",
        headers={
            "x-github-delivery": "delivery-1",
            "x-github-event": "pull_request",
            "x-hub-signature-256": "sha256=" + "0" * 64,
        },
    )

    assert response.status_code == 401


def test_webhook_rejects_invalid_content_length() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/github/webhook",
        content=b"{}",
        headers={
            "content-length": "bad",
            "x-github-delivery": "delivery-1",
            "x-github-event": "pull_request",
            "x-hub-signature-256": signature(b"{}"),
        },
    )

    assert response.status_code == 400


def test_webhook_rejects_signed_malformed_json_as_client_error() -> None:
    client = TestClient(app)
    body = b"{"
    response = client.post(
        "/api/github/webhook",
        content=body,
        headers={
            "x-github-delivery": "delivery-2",
            "x-github-event": "pull_request",
            "x-hub-signature-256": signature(body),
        },
    )

    assert response.status_code == 400


def test_webhook_rejects_a_partial_pull_request_payload() -> None:
    """GitHubDelivery stays complete. A fixture that only has action is what was wrong."""
    client = TestClient(app)
    body = b'{"action":"opened"}'
    response = client.post(
        "/api/github/webhook",
        content=body,
        headers={
            "x-github-delivery": "delivery-partial",
            "x-github-event": "pull_request",
            "x-hub-signature-256": signature(body),
        },
    )
    assert response.status_code == 400
    with connection() as conn:
        row = conn.execute("select count(*) as count from review_jobs").fetchone()
    assert row is not None
    assert row["count"] == 0


def test_webhook_enqueues_pull_request() -> None:
    _insert_installation()
    client = TestClient(app)
    payload = _pull_request_payload(action="opened", draft=False)
    response = _post_webhook(client, "delivery-3", payload)
    duplicate = _post_webhook(client, "delivery-3", payload)

    assert response.status_code == 202
    assert response.json() == {"result": "enqueued"}
    assert duplicate.status_code == 200
    assert duplicate.json() == {"result": "duplicate"}

    with connection() as conn:
        row = conn.execute("select count(*) as count from review_jobs").fetchone()

    assert row is not None
    assert row["count"] == 1


def test_webhook_ignores_an_opened_draft_and_writes_no_job() -> None:
    _insert_installation()
    client = TestClient(app)
    response = _post_webhook(
        client, "delivery-draft", _pull_request_payload(action="opened", draft=True)
    )
    assert response.status_code == 200
    assert response.json() == {"result": "ignored"}
    with connection() as conn:
        row = conn.execute("select count(*) as count from review_jobs").fetchone()
    assert row is not None
    assert row["count"] == 0


def test_webhook_cancels_a_closed_pull_request() -> None:
    _insert_installation()
    client = TestClient(app)
    opened = _post_webhook(
        client, "delivery-open-then-close", _pull_request_payload(action="opened")
    )
    assert opened.status_code == 202
    closed = _post_webhook(client, "delivery-closed", _pull_request_payload(action="closed"))
    assert closed.status_code == 200
    assert closed.json() == {"result": "cancelled"}
    with connection() as conn:
        row = conn.execute(
            "select status from review_jobs where delivery_id = %s",
            ("delivery-open-then-close",),
        ).fetchone()
    assert row is not None
    assert row["status"] == "cancelled"


def test_webhook_cancels_converted_to_draft() -> None:
    _insert_installation()
    client = TestClient(app)
    opened = _post_webhook(
        client, "delivery-open-then-draft", _pull_request_payload(action="opened")
    )
    assert opened.status_code == 202
    converted = _post_webhook(
        client,
        "delivery-converted",
        _pull_request_payload(action="converted_to_draft", draft=True),
    )
    assert converted.status_code == 200
    assert converted.json() == {"result": "cancelled"}
    with connection() as conn:
        row = conn.execute(
            "select status from review_jobs where delivery_id = %s",
            ("delivery-open-then-draft",),
        ).fetchone()
    assert row is not None
    assert row["status"] == "cancelled"


def test_webhook_cancel_tells_a_running_runner_the_job_is_cancelled(
    make_verified_installation_access: Any,
) -> None:
    from test_runner_job_protocol import pair_runner_assigned_to_repo

    _insert_installation()
    credential = pair_runner_assigned_to_repo(
        INSTALLATION_ID, REPOSITORY_ID, make_verified_installation_access
    )
    client = TestClient(app)
    opened = _post_webhook(
        client, "delivery-running-then-close", _pull_request_payload(action="opened")
    )
    assert opened.status_code == 202
    claimed = client.post(
        "/api/runner/jobs/claim",
        headers={"authorization": f"Bearer {credential.credential}"},
    )
    assert claimed.status_code == 200
    envelope = claimed.json()
    closed = _post_webhook(
        client, "delivery-running-closed", _pull_request_payload(action="closed")
    )
    assert closed.status_code == 200
    assert closed.json() == {"result": "cancelled"}
    heartbeat = client.post(
        f"/api/runner/jobs/{envelope['job_id']}/heartbeat",
        headers={"authorization": f"Bearer {credential.credential}"},
        json={"lease_token": envelope["lease_token"]},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json() == {"status": "cancelled"}
