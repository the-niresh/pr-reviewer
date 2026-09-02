"""Authenticated runner installation snapshots come from its stored pairing identity."""

from __future__ import annotations

from fastapi.testclient import TestClient
from test_token_broker import pair_runner_assigned_to_repo

from pr_reviewer.web.app import app


def test_runner_installation_snapshot_returns_only_the_callers_assignment(
    make_verified_installation_access: object,
) -> None:
    from test_runner_pairing import insert_installation

    installation_id = 98_001
    repository_id = 98_101
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, repository_id, make_verified_installation_access
    )

    response = TestClient(app).get(
        "/api/runner/installation",
        headers={"authorization": f"Bearer {credential.credential}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "github_login": "acme",
        "github_user_id": 42,
        "installation_id": installation_id,
        "repositories": [
            {"github_repository_id": repository_id, "name": "widgets"},
        ],
    }


def test_runner_installation_snapshot_rejects_missing_or_invalid_runner_credential() -> None:
    client = TestClient(app)

    assert client.get("/api/runner/installation").status_code == 401
    assert client.get(
        "/api/runner/installation", headers={"authorization": "Bearer not-a-credential"}
    ).status_code == 401
