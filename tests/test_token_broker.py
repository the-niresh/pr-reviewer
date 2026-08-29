"""Tests for the short-lived GitHub token broker (Runtime Task 4).

issue_job_token exchanges a valid job lease for an installation token, scoped to that job's
repository and to read-only permissions. Denial here reuses JobProtocolDenied from Task 3, on
purpose: a caller presenting a lease that is wrong, expired, superseded, already finished, or for
a repository they are no longer assigned to is not authorised to learn which of those is true, the
same indistinguishability rule as heartbeat_job and acknowledge_job. There is no second denial
type to invent; the lease check IS the token check.

Every denial test injects a GitHubAppClient wired to an ExplodingHttpClient. A green run here
proves the denial happened before any call reached GitHub, not just that the return value looked
right.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from pr_reviewer.contracts.runner import (
    AuthenticatedRunner,
    JobEnvelope,
    RunnerCredential,
)
from pr_reviewer.control_plane.runner_jobs import claim_job
from pr_reviewer.db.client import connection
from pr_reviewer.github.app_client import GitHubAppClient
from pr_reviewer.github.tokens import GitHubAppSettings
from pr_reviewer.jobs import enqueue_review_job
from pr_reviewer.web.app import app

VerifiedAccessFactory = Any

BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
NEWER_HEAD_SHA = "c" * 40


def _rsa_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


_TEST_PRIVATE_KEY = _rsa_private_key_pem()


class ExplodingHttpClient:
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        del headers, timeout, json
        raise AssertionError(f"unexpected GitHub call: POST {url}, denial should happen first")


class CapturingHttpClient:
    def __init__(self, response_json: dict[str, object]) -> None:
        self.calls: list[dict[str, object]] = []
        self._response_json = response_json

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        self.calls.append({"url": url, "headers": headers, "timeout": timeout, "json": json})
        return httpx.Response(
            201,
            request=httpx.Request("POST", url),
            json=self._response_json,
        )


def exploding_app_client() -> GitHubAppClient:
    return GitHubAppClient(
        settings=GitHubAppSettings(app_id="unused", private_key="unused"),
        client=ExplodingHttpClient(),
    )


def capturing_app_client(
    response_json: dict[str, object]
) -> tuple[GitHubAppClient, CapturingHttpClient]:
    capturing = CapturingHttpClient(response_json)
    app_client = GitHubAppClient(
        settings=GitHubAppSettings(app_id="123", private_key=_TEST_PRIVATE_KEY),
        client=capturing,
    )
    return app_client, capturing


def insert_installation(installation_id: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (installation_id, "acme"),
        )


def pair_runner_assigned_to_repo(
    installation_id: int,
    github_repository_id: int,
    make_verified_installation_access: VerifiedAccessFactory,
    device_name: str = "laptop",
    repo_name: str = "widgets",
) -> RunnerCredential:
    import hashlib

    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    def sha256_hex(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    verifier = f"verifier-for-{device_name}"
    challenge_result = create_pairing_code(device_name, sha256_hex(verifier))
    access = make_verified_installation_access(
        42, installation_id, {github_repository_id: repo_name}
    )
    approve_pairing(challenge_result.code, access, [github_repository_id])
    result = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(result, RunnerCredential)
    return result


def authenticate(credential: str) -> AuthenticatedRunner:
    from pr_reviewer.control_plane.runner_auth import authenticate_runner

    result = authenticate_runner(credential)
    assert isinstance(result, AuthenticatedRunner)
    return result


def enqueue_pull_request_job(
    delivery_id: str,
    installation_id: int,
    github_repository_id: int,
    pull_request_number: int = 12,
    base_sha: str = BASE_SHA,
    head_sha: str = HEAD_SHA,
    repo_name: str = "widgets",
) -> None:
    payload = {
        "action": "opened",
        "installation": {"id": installation_id},
        "repository": {"id": github_repository_id, "name": repo_name},
        "pull_request": {
            "number": pull_request_number,
            "base": {"sha": base_sha},
            "head": {"sha": head_sha},
        },
    }
    assert enqueue_review_job(delivery_id, "pull_request", payload) == "enqueued"


def assert_value_not_persisted_anywhere(value: str) -> None:
    from psycopg import sql

    with connection() as conn:
        tables = conn.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_type = 'BASE TABLE'"
        ).fetchall()
        for table in tables:
            table_name = str(table["table_name"])
            rows = conn.execute(
                sql.SQL("select * from {}").format(sql.Identifier(table_name))
            ).fetchall()
            for row in rows:
                assert value not in str(dict(row)), f"leaked into {table_name}: {dict(row)}"


def test_wrong_runner_cannot_mint_a_token_for_someone_elses_job(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobProtocolDenied
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9201
    owner_repo = 92101
    intruder_repo = 92102
    insert_installation(installation_id)
    owner = pair_runner_assigned_to_repo(
        installation_id, owner_repo, make_verified_installation_access, "owner"
    )
    intruder = pair_runner_assigned_to_repo(
        installation_id, intruder_repo, make_verified_installation_access, "intruder"
    )
    enqueue_pull_request_job("delivery-token-wrong-runner", installation_id, owner_repo)
    owner_runner = authenticate(owner.credential)
    envelope = claim_job(owner_runner)
    assert isinstance(envelope, JobEnvelope)
    intruder_runner = authenticate(intruder.credential)

    with pytest.raises(JobProtocolDenied) as denied:
        issue_job_token(
            intruder_runner.runner_id,
            envelope.job_id,
            envelope.lease_token,
            app_client=exploding_app_client(),
        )
    assert denied.value.reason == "invalid_or_expired"


def test_runner_no_longer_assigned_to_the_repository_is_denied_a_token(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobProtocolDenied
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9202
    github_repository_id = 92201
    insert_installation(installation_id)
    original = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access, "original"
    )
    enqueue_pull_request_job("delivery-token-reassigned", installation_id, github_repository_id)
    runner = authenticate(original.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    # The repository is reassigned to a different runner after the lease was already claimed.
    with connection() as conn, conn.transaction():
        conn.execute(
            "delete from repository_assignments where runner_id = %s",
            (str(runner.runner_id),),
        )
    pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access, "replacement"
    )

    with pytest.raises(JobProtocolDenied) as denied:
        issue_job_token(
            runner.runner_id,
            envelope.job_id,
            envelope.lease_token,
            app_client=exploding_app_client(),
        )
    assert denied.value.reason == "invalid_or_expired"


def test_expired_lease_cannot_mint_a_token(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobProtocolDenied
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9203
    github_repository_id = 92301
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-token-expired", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)
    with connection() as conn, conn.transaction():
        conn.execute(
            "update review_jobs set locked_until = now() - interval '1 second' where id = %s",
            (str(envelope.job_id),),
        )

    with pytest.raises(JobProtocolDenied) as denied:
        issue_job_token(
            runner.runner_id,
            envelope.job_id,
            envelope.lease_token,
            app_client=exploding_app_client(),
        )
    assert denied.value.reason == "invalid_or_expired"


def test_stale_head_sha_job_is_superseded_and_cannot_mint_a_token(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobProtocolDenied
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9204
    github_repository_id = 92401
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job(
        "delivery-token-stale-old", installation_id, github_repository_id, head_sha=HEAD_SHA
    )
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    enqueue_pull_request_job(
        "delivery-token-stale-new",
        installation_id,
        github_repository_id,
        head_sha=NEWER_HEAD_SHA,
    )

    with pytest.raises(JobProtocolDenied) as denied:
        issue_job_token(
            runner.runner_id,
            envelope.job_id,
            envelope.lease_token,
            app_client=exploding_app_client(),
        )
    assert denied.value.reason == "invalid_or_expired"


def test_revoked_installation_cannot_mint_a_token(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobProtocolDenied
    from pr_reviewer.control_plane.repository_policy import revoke_installation
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9205
    github_repository_id = 92501
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job(
        "delivery-token-revoked-installation", installation_id, github_repository_id
    )
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    revoke_installation(installation_id)

    with pytest.raises(JobProtocolDenied) as denied:
        issue_job_token(
            runner.runner_id,
            envelope.job_id,
            envelope.lease_token,
            app_client=exploding_app_client(),
        )
    assert denied.value.reason == "invalid_or_expired"


def test_token_replay_after_job_completion_is_denied(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import JobAcknowledgement, JobProtocolDenied
    from pr_reviewer.control_plane.runner_jobs import acknowledge_job
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9206
    github_repository_id = 92601
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-token-replay", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    result = JobAcknowledgement(
        terminal_state="succeeded",
        error_class=None,
        input_tokens=1,
        output_tokens=1,
        cost_usd=Decimal("0.010000"),
        latency_ms=1,
        local_result_hash="f" * 64,
    )
    acknowledge_job(runner.runner_id, envelope.job_id, envelope.lease_token, result)

    with pytest.raises(JobProtocolDenied) as denied:
        issue_job_token(
            runner.runner_id,
            envelope.job_id,
            envelope.lease_token,
            app_client=exploding_app_client(),
        )
    assert denied.value.reason == "invalid_or_expired"


def test_issued_token_is_scoped_to_the_job_repository_and_minimal_read_permissions(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9207
    github_repository_id = 92701
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-token-scope", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    app_client, capturing = capturing_app_client(
        {"token": "ghs_scoped", "expires_at": "2026-01-01T00:10:00Z"}
    )

    token = issue_job_token(
        runner.runner_id, envelope.job_id, envelope.lease_token, app_client=app_client
    )

    assert len(capturing.calls) == 1
    body = capturing.calls[0]["json"]
    assert isinstance(body, dict)
    assert body["repository_ids"] == [github_repository_id]
    permissions = body["permissions"]
    assert isinstance(permissions, dict)
    assert permissions, "must not mint an unscoped, all-permission token"
    assert set(permissions) <= {"contents", "pull_requests"}
    assert all(scope == "read" for scope in permissions.values())
    assert "administration" not in permissions
    assert "actions" not in permissions
    assert token.token == "ghs_scoped"
    assert token.github_repository_id == github_repository_id


def test_token_route_rejects_missing_and_unknown_credential(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    installation_id = 9209
    github_repository_id = 92901
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-token-http-auth", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    client = TestClient(app)

    missing = client.post(
        f"/api/runner/jobs/{envelope.job_id}/token",
        json={"lease_token": envelope.lease_token},
    )
    assert missing.status_code == 401

    unknown = client.post(
        f"/api/runner/jobs/{envelope.job_id}/token",
        json={"lease_token": envelope.lease_token},
        headers={"authorization": "Bearer never-issued"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == "unknown_credential"


def test_token_route_returns_409_for_a_wrong_lease(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    installation_id = 9210
    github_repository_id = 93001
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-token-http-lease", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    client = TestClient(app)

    wrong_lease = client.post(
        f"/api/runner/jobs/{envelope.job_id}/token",
        json={"lease_token": "not-the-lease-token"},
        headers={"authorization": f"Bearer {credential.credential}"},
    )
    assert wrong_lease.status_code == 409
    assert wrong_lease.json()["detail"] == "invalid_or_expired"


def test_token_route_returns_200_with_the_minted_token_for_a_valid_lease(
    make_verified_installation_access: VerifiedAccessFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pr_reviewer.contracts.runner import GitHubJobToken
    from pr_reviewer.control_plane import runner_jobs

    installation_id = 9211
    github_repository_id = 93101
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-token-http-success", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    def fake_issue_job_token(
        runner_id: object, job_id: object, lease_token: str, **_: object
    ) -> GitHubJobToken:
        assert lease_token == envelope.lease_token
        return GitHubJobToken(
            token="ghs_http_success",
            github_repository_id=github_repository_id,
            expires_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(runner_jobs, "issue_job_token", fake_issue_job_token)

    client = TestClient(app)
    response = client.post(
        f"/api/runner/jobs/{envelope.job_id}/token",
        json={"lease_token": envelope.lease_token},
        headers={"authorization": f"Bearer {credential.credential}"},
    )
    assert response.status_code == 200
    assert response.json()["token"] == "ghs_http_success"
    assert response.json()["github_repository_id"] == github_repository_id


def test_issued_token_is_never_persisted_in_neon(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.control_plane.token_broker import issue_job_token

    installation_id = 9208
    github_repository_id = 92801
    insert_installation(installation_id)
    credential = pair_runner_assigned_to_repo(
        installation_id, github_repository_id, make_verified_installation_access
    )
    enqueue_pull_request_job("delivery-token-not-persisted", installation_id, github_repository_id)
    runner = authenticate(credential.credential)
    envelope = claim_job(runner)
    assert isinstance(envelope, JobEnvelope)

    secret_marker = "ghs_do_not_persist_" + uuid.uuid4().hex
    app_client, _ = capturing_app_client(
        {"token": secret_marker, "expires_at": "2026-01-01T00:10:00Z"}
    )

    token = issue_job_token(
        runner.runner_id, envelope.job_id, envelope.lease_token, app_client=app_client
    )
    assert token.token == secret_marker

    assert_value_not_persisted_anywhere(secret_marker)
