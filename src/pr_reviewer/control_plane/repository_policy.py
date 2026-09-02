from __future__ import annotations

import hashlib
import uuid

import psycopg
from psycopg import Connection

from pr_reviewer.contracts.runner import (
    AssignmentGranted,
    AssignmentRefused,
    AuthorizationDenied,
    RepositoryAuthorization,
    RunnerCapabilities,
    RunnerRef,
)
from pr_reviewer.db.client import Row, connection


def hash_runner_credential(credential: str) -> str:
    # Runner credentials are opaque, high-entropy generated secrets, not user passwords, so a
    # deterministic hash (no per-credential salt) is the same tradeoff GitHub and Stripe make for
    # API keys: brute force is infeasible against the credential's own entropy, and a deterministic
    # hash lets a lookup compare a presented credential without ever storing it in the clear.
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


def register_installation(installation_id: int, account_login: str) -> None:
    with connection() as conn:
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (installation_id, account_login),
        )


def revoke_installation(installation_id: int) -> None:
    with connection() as conn:
        conn.execute(
            "update installations set revoked_at = now() where id = %s and revoked_at is null",
            (installation_id,),
        )


def register_repository(installation_id: int, github_repository_id: int, name: str) -> uuid.UUID:
    with connection() as conn:
        row = conn.execute(
            """
            insert into repositories (installation_id, github_repository_id, name)
            values (%s, %s, %s)
            returning id
            """,
            (installation_id, github_repository_id, name),
        ).fetchone()
    assert row is not None
    return uuid.UUID(str(row["id"]))


def rename_repository(repository_id: uuid.UUID, new_name: str) -> None:
    with connection() as conn:
        conn.execute(
            "update repositories set name = %s, updated_at = now() where id = %s",
            (new_name, str(repository_id)),
        )


def register_runner(
    conn: Connection[Row],
    device_name: str,
    credential: str,
    capabilities: RunnerCapabilities,
    *,
    github_user_id: int | None = None,
    installation_id: int | None = None,
) -> uuid.UUID:
    # conn is required, not optional, so a caller composing this into a larger transaction (see
    # control_plane/pairing.py's exchange_pairing_code) always gets exactly that: never a second,
    # independent connection silently committing a runner row the caller's own transaction later
    # rolls back around.
    if (github_user_id is None) != (installation_id is None):
        raise ValueError("runner pairing identity requires both github user and installation")

    row = conn.execute(
        """
        insert into runners (
          device_name, credential_hash, mode, docker_available, retrieval_available,
          verification_available, platform, version, github_user_id, installation_id
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            device_name,
            hash_runner_credential(credential),
            capabilities.mode,
            capabilities.docker_available,
            capabilities.retrieval_available,
            capabilities.verification_available,
            capabilities.platform,
            capabilities.version,
            github_user_id,
            installation_id,
        ),
    ).fetchone()
    assert row is not None
    return uuid.UUID(str(row["id"]))


def revoke_runner(runner_id: uuid.UUID) -> None:
    with connection() as conn:
        conn.execute(
            "update runners set revoked_at = now() where id = %s and revoked_at is null",
            (str(runner_id),),
        )


def assign_repository_to_runner(
    conn: Connection[Row],
    repository_id: uuid.UUID,
    runner_id: uuid.UUID,
) -> AssignmentGranted | AssignmentRefused:
    # conn is required for the same reason as register_runner above. The inner conn.transaction()
    # below becomes a savepoint when conn is already inside a caller's transaction (psycopg3's
    # nested-transaction behaviour), so a refusal here rolls back only this insert, not whatever
    # the caller already did, and the caller decides what to do about the refusal from there.
    try:
        with conn.transaction():
            conn.execute(
                """
                insert into repository_assignments (repository_id, runner_id)
                values (%s, %s)
                """,
                (str(repository_id), str(runner_id)),
            )
    except psycopg.errors.UniqueViolation:
        # Refused, not auto-revoked: the existing assignment is left exactly as it was, and the
        # caller is told who holds it instead of silently stealing the repository.
        row = conn.execute(
            """
            select runners.id as runner_id, runners.device_name as device_name
            from repository_assignments
            join runners on runners.id = repository_assignments.runner_id
            where repository_assignments.repository_id = %s
            """,
            (str(repository_id),),
        ).fetchone()
        assert row is not None
        return AssignmentRefused(
            repository_id=repository_id,
            active_runner=RunnerRef(
                runner_id=uuid.UUID(str(row["runner_id"])),
                device_name=str(row["device_name"]),
            ),
        )

    return AssignmentGranted(repository_id=repository_id, runner_id=runner_id)


def authorize_repository(
    installation_id: int,
    github_repository_id: int,
    runner_id: uuid.UUID,
) -> RepositoryAuthorization | AuthorizationDenied:
    with connection() as conn:
        installation = conn.execute(
            "select revoked_at from installations where id = %s",
            (installation_id,),
        ).fetchone()
        if installation is None:
            return AuthorizationDenied(reason="unknown_installation")
        if installation["revoked_at"] is not None:
            return AuthorizationDenied(reason="revoked_installation")

        repository = conn.execute(
            """
            select id from repositories
            where installation_id = %s and github_repository_id = %s
            """,
            (installation_id, github_repository_id),
        ).fetchone()
        if repository is None:
            # Deliberately indistinguishable from "nobody has ever registered this repository":
            # telling the two cases apart would require a lookup scoped only by
            # github_repository_id, with no installation_id, which is a cross-tenant read on its
            # own even though the result here would only be used to pick a reason string. A denial
            # reason is part of the tenancy boundary (phase-2-security-design-gate.md, section 6).
            return AuthorizationDenied(reason="unknown_repository")

        runner = conn.execute(
            "select revoked_at from runners where id = %s",
            (str(runner_id),),
        ).fetchone()
        if runner is None:
            return AuthorizationDenied(reason="unknown_runner")
        if runner["revoked_at"] is not None:
            return AuthorizationDenied(reason="revoked_runner")

        assignment = conn.execute(
            """
            select 1 from repository_assignments
            where repository_id = %s and runner_id = %s
            """,
            (str(repository["id"]), str(runner_id)),
        ).fetchone()
        if assignment is None:
            return AuthorizationDenied(reason="runner_not_assigned_to_repository")

        return RepositoryAuthorization(
            installation_id=installation_id,
            github_repository_id=github_repository_id,
            repository_id=uuid.UUID(str(repository["id"])),
            runner_id=runner_id,
        )
