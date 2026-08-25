from __future__ import annotations

import hmac
from hashlib import sha256

from fastapi.testclient import TestClient

from pr_reviewer.db.client import connection
from pr_reviewer.web.app import app


def signature(body: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()


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


def test_webhook_enqueues_pull_request() -> None:
    client = TestClient(app)
    body = b'{"action":"opened"}'
    headers = {
        "x-github-delivery": "delivery-3",
        "x-github-event": "pull_request",
        "x-hub-signature-256": signature(body),
    }

    response = client.post("/api/github/webhook", content=body, headers=headers)
    duplicate = client.post("/api/github/webhook", content=body, headers=headers)

    assert response.status_code == 202
    assert response.json() == {"result": "enqueued"}
    assert duplicate.status_code == 200
    assert duplicate.json() == {"result": "duplicate"}

    with connection() as conn:
        row = conn.execute("select count(*) as count from review_jobs").fetchone()

    assert row is not None
    assert row["count"] == 1
