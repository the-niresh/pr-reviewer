"""Runner installation-token endpoint tests.

The guarded break is removing the assignment query from
``issue_runner_installation_token``.  That must deny a runner paired to a
different installation before a GitHub request is made.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from test_token_broker import (
    CapturingHttpClient,
    authenticate,
    capturing_app_client,
    insert_installation,
    pair_runner_assigned_to_repo,
)

from pr_reviewer.github.app_client import GitHubAppClient
from pr_reviewer.web.app import app


def _capturing_app_client() -> tuple[GitHubAppClient, CapturingHttpClient]:
    return capturing_app_client(
        {"token": "ghs_runner_installation", "expires_at": "2026-01-01T01:00:00Z"}
    )


def test_paired_runner_mints_an_installation_token_scoped_to_its_repositories(
    make_verified_installation_access: object,
) -> None:
    from pr_reviewer.control_plane.installation_token import issue_runner_installation_token

    installation_id = 97_001
    repository_id = 97_101
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, repository_id, make_verified_installation_access
    )
    app_client, github = _capturing_app_client()

    token = issue_runner_installation_token(
        authenticate(credential.credential).runner_id,
        installation_id,
        app_client=app_client,
    )

    assert token.token == "ghs_runner_installation"
    assert token.expires_at == datetime(2026, 1, 1, 1, tzinfo=UTC)
    assert len(github.calls) == 1
    assert github.calls[0]["url"] == (
        "https://api.github.com/app/installations/97001/access_tokens"
    )
    assert github.calls[0]["json"] == {
        "repository_ids": [repository_id],
        "permissions": {"contents": "read", "pull_requests": "read"},
    }


def test_runner_cannot_mint_a_token_for_an_installation_it_is_not_paired_to(
    make_verified_installation_access: object,
) -> None:
    from pr_reviewer.control_plane.installation_token import (
        RunnerInstallationTokenDenied,
        issue_runner_installation_token,
    )

    paired_installation_id = 97_002
    other_installation_id = 97_003
    insert_installation(paired_installation_id)
    insert_installation(other_installation_id)
    credential = pair_runner_assigned_to_repo(
        paired_installation_id, 97_102, make_verified_installation_access
    )
    pair_runner_assigned_to_repo(
        other_installation_id, 97_103, make_verified_installation_access, "other-runner"
    )
    app_client, github = _capturing_app_client()

    with pytest.raises(RunnerInstallationTokenDenied) as denied:
        issue_runner_installation_token(
            authenticate(credential.credential).runner_id,
            other_installation_id,
            app_client=app_client,
        )

    assert denied.value.reason == "installation_not_assigned"
    assert github.calls == []


def test_installation_token_route_authenticates_the_runner(
    make_verified_installation_access: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pr_reviewer.control_plane import pairing_api
    from pr_reviewer.control_plane.installation_token import RunnerInstallationToken

    installation_id = 97_004
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, 97_104, make_verified_installation_access
    )

    def issue(
        runner_id: object, requested_installation_id: int
    ) -> RunnerInstallationToken:
        assert runner_id == authenticate(credential.credential).runner_id
        assert requested_installation_id == installation_id
        return RunnerInstallationToken(
            token="ghs_route_token", expires_at=datetime(2026, 1, 1, 1, tzinfo=UTC)
        )

    monkeypatch.setattr(pairing_api, "issue_runner_installation_token", issue)
    client = TestClient(app)

    missing = client.post(f"/api/runner/installations/{installation_id}/token")
    assert missing.status_code == 401

    response = client.post(
        f"/api/runner/installations/{installation_id}/token",
        headers={"authorization": f"Bearer {credential.credential}"},
    )
    assert response.status_code == 200
    assert response.json()["token"] == "ghs_route_token"
