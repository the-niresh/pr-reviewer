"""Tests for runner credential authentication and rotation (Runtime Task 2).

authenticate_runner and rotate_runner_credential both start from a credential the caller already
possesses, unlike pairing where the caller is proving they hold a code they might have only
guessed. Possessing a credential is itself evidence of prior legitimate issuance, so "this
credential does not match any runner" and "this credential belonged to a runner that has since
been revoked" are allowed to be distinguishable here, the same way Task 1's authorize_repository
already distinguishes unknown_runner from revoked_runner.
"""

from __future__ import annotations

from collections.abc import Callable

from pr_reviewer.db.client import connection

VerifiedAccessFactory = Callable[[int, int], object]


def insert_installation(installation_id: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (installation_id, "acme"),
        )


def sha256_hex(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pair_and_exchange_a_runner(
    installation_id: int,
    make_verified_installation_access: VerifiedAccessFactory,
    device_name: str = "laptop",
) -> object:
    from pr_reviewer.contracts.runner import RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    verifier = f"verifier-for-{device_name}"
    challenge_result = create_pairing_code(device_name, sha256_hex(verifier))
    access = make_verified_installation_access(42, installation_id)
    approve_pairing(challenge_result.code, access, [])

    result = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(result, RunnerCredential)
    return result


def test_authenticate_runner_succeeds_for_a_valid_credential(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import AuthenticatedRunner
    from pr_reviewer.control_plane.runner_auth import authenticate_runner

    installation_id = 6001
    insert_installation(installation_id)
    credential = pair_and_exchange_a_runner(installation_id, make_verified_installation_access)

    result = authenticate_runner(credential.credential)
    assert isinstance(result, AuthenticatedRunner)
    assert result.runner_id == credential.runner_id


def test_authenticate_runner_denied_for_unknown_credential() -> None:
    from pr_reviewer.contracts.runner import RunnerAuthDenied
    from pr_reviewer.control_plane.runner_auth import authenticate_runner

    result = authenticate_runner("a-credential-nobody-ever-issued")
    assert isinstance(result, RunnerAuthDenied)
    assert result.reason == "unknown_credential"


def test_authenticate_runner_denied_for_revoked_runner(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import RunnerAuthDenied
    from pr_reviewer.control_plane.runner_auth import authenticate_runner

    installation_id = 6002
    insert_installation(installation_id)
    credential = pair_and_exchange_a_runner(installation_id, make_verified_installation_access)

    with connection() as conn, conn.transaction():
        conn.execute("update runners set revoked_at = now() where id = %s", (credential.runner_id,))

    result = authenticate_runner(credential.credential)
    assert isinstance(result, RunnerAuthDenied)
    assert result.reason == "revoked_runner"


def test_rotate_runner_credential_issues_new_and_invalidates_old_atomically(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import AuthenticatedRunner, RunnerAuthDenied, RunnerCredential
    from pr_reviewer.control_plane.runner_auth import authenticate_runner, rotate_runner_credential

    installation_id = 6003
    insert_installation(installation_id)
    credential = pair_and_exchange_a_runner(installation_id, make_verified_installation_access)

    rotated = rotate_runner_credential(credential.runner_id, credential.credential)
    assert isinstance(rotated, RunnerCredential)
    assert rotated.credential != credential.credential

    old_auth = authenticate_runner(credential.credential)
    assert isinstance(old_auth, RunnerAuthDenied)
    assert old_auth.reason == "unknown_credential"

    new_auth = authenticate_runner(rotated.credential)
    assert isinstance(new_auth, AuthenticatedRunner)
    assert new_auth.runner_id == credential.runner_id


def test_rotate_runner_credential_denied_for_wrong_current_credential(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import RunnerAuthDenied
    from pr_reviewer.control_plane.runner_auth import rotate_runner_credential

    installation_id = 6004
    insert_installation(installation_id)
    credential = pair_and_exchange_a_runner(installation_id, make_verified_installation_access)

    result = rotate_runner_credential(credential.runner_id, "not-the-real-credential")
    assert isinstance(result, RunnerAuthDenied)
    assert result.reason == "unknown_credential"


def test_rotate_runner_credential_denied_for_revoked_runner(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import RunnerAuthDenied
    from pr_reviewer.control_plane.runner_auth import rotate_runner_credential

    installation_id = 6005
    insert_installation(installation_id)
    credential = pair_and_exchange_a_runner(installation_id, make_verified_installation_access)

    with connection() as conn, conn.transaction():
        conn.execute("update runners set revoked_at = now() where id = %s", (credential.runner_id,))

    result = rotate_runner_credential(credential.runner_id, credential.credential)
    assert isinstance(result, RunnerAuthDenied)
    assert result.reason == "revoked_runner"
