"""Runner credential authentication and rotation (Runtime Task 2).

Unlike pairing, a caller here already possesses a credential, which is itself evidence of prior
legitimate issuance. So unknown_credential and revoked_runner are allowed to be distinguishable,
the same way Task 1's authorize_repository already distinguishes unknown_runner from
revoked_runner.
"""

from __future__ import annotations

import secrets
import uuid

from pr_reviewer.contracts.runner import AuthenticatedRunner, RunnerAuthDenied, RunnerCredential
from pr_reviewer.control_plane.repository_policy import hash_runner_credential
from pr_reviewer.db.client import connection


def authenticate_runner(credential: str) -> AuthenticatedRunner | RunnerAuthDenied:
    credential_hash = hash_runner_credential(credential)
    with connection() as conn:
        row = conn.execute(
            "select id, device_name, mode, revoked_at from runners where credential_hash = %s",
            (credential_hash,),
        ).fetchone()

    if row is None:
        return RunnerAuthDenied(reason="unknown_credential")
    if row["revoked_at"] is not None:
        return RunnerAuthDenied(reason="revoked_runner")

    return AuthenticatedRunner(
        runner_id=uuid.UUID(str(row["id"])),
        device_name=str(row["device_name"]),
        mode=row["mode"],
    )


def rotate_runner_credential(
    runner_id: uuid.UUID, current_credential: str
) -> RunnerCredential | RunnerAuthDenied:
    current_hash = hash_runner_credential(current_credential)
    new_credential = secrets.token_urlsafe(32)
    new_hash = hash_runner_credential(new_credential)

    with connection() as conn, conn.transaction():
        # Locking the row here, inside the one transaction that both reads and writes it, is what
        # makes the swap atomic: nothing else can revoke or rotate this runner between the check
        # and the update, so there is no window where both credentials work and none where neither
        # does.
        row = conn.execute(
            "select revoked_at from runners where id = %s and credential_hash = %s for update",
            (str(runner_id), current_hash),
        ).fetchone()
        if row is None:
            return RunnerAuthDenied(reason="unknown_credential")
        if row["revoked_at"] is not None:
            return RunnerAuthDenied(reason="revoked_runner")

        conn.execute(
            "update runners set credential_hash = %s where id = %s and credential_hash = %s",
            (new_hash, str(runner_id), current_hash),
        )

    return RunnerCredential(runner_id=runner_id, credential=new_credential)
