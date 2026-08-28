"""One-time runner pairing (Runtime Task 2).

A pairing code moves through exactly three states, in order, each guarded by its own function:
created (create_pairing_code), approved (approve_pairing), exchanged (exchange_pairing_code).
Approval only records a decision: which installation, which repositories. It never creates a
runner or a repository_assignments row, so an approved-but-abandoned pairing cannot permanently
lock a repository away from a later attempt. Exchange is the only place a runner and its
assignments come into existence, and it does so inside one transaction, so a refusal there (see
repository_policy.assign_repository_to_runner) leaves no partial runner behind.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence

from psycopg import Connection

from pr_reviewer.contracts.runner import (
    AssignmentRefused,
    PairingApproved,
    PairingChallenge,
    PairingDenied,
    RunnerCapabilities,
    RunnerCredential,
    VerifiedInstallationAccess,
)
from pr_reviewer.control_plane.repository_policy import (
    assign_repository_to_runner,
    hash_runner_credential,
    register_runner,
)
from pr_reviewer.db.client import Row, connection

# A runner that has only just been paired has no verified capabilities yet; it reports its real
# ones on its first authenticated call after exchange. Analysis-only, no docker, no retrieval, no
# verification is the least-privileged starting point.
_INITIAL_RUNNER_CAPABILITIES = RunnerCapabilities(
    mode="analysis_only",
    docker_available=False,
    retrieval_available=False,
    verification_available=False,
    platform="unknown",
    version="unknown",
)


class _ExchangeConflict(Exception):
    """Internal control-flow only: forces the exchange transaction to roll back the runner it just
    created, because a repository it was supposed to claim is already held by another runner.
    """

    def __init__(self, refused: AssignmentRefused) -> None:
        self.refused = refused


def verify_installation_access(
    github_user_id: int, installation_id: int, repositories: dict[int, str]
) -> VerifiedInstallationAccess:
    """The one construction site for VerifiedInstallationAccess in src/.

    Runtime Task 2 does not build GitHub OAuth, so this function has no way yet to actually check
    that github_user_id controls installation_id; Task 2A replaces this body with a real call to
    GitHub's /user/installations using the user's OAuth token, and a real listing of that
    installation's repositories. Keeping construction behind one named function, instead of
    building the value object inline wherever it is needed, means that swap touches exactly this
    file and nothing that calls approve_pairing has to change.
    """
    return VerifiedInstallationAccess(
        github_user_id=github_user_id,
        installation_id=installation_id,
        repositories=repositories,
    )


def create_pairing_code(device_name: str, challenge: str) -> PairingChallenge:
    # PKCE: the runner already generated its own verifier and sends only the challenge (a hash of
    # the verifier) here. It presents the verifier itself at exchange time, and only a value that
    # hashes back to this challenge is accepted.
    code = secrets.token_urlsafe(32)
    code_hash = hash_runner_credential(code)
    with connection() as conn:
        row = conn.execute(
            """
            insert into pairing_codes (device_name, code_hash, challenge)
            values (%s, %s, %s)
            returning created_at
            """,
            (device_name, code_hash, challenge),
        ).fetchone()
    assert row is not None
    return PairingChallenge(code=code, expires_at=row["created_at"])


def _upsert_repository(
    conn: Connection[Row], installation_id: int, github_repository_id: int, name: str
) -> uuid.UUID:
    row = conn.execute(
        """
        insert into repositories (installation_id, github_repository_id, name)
        values (%s, %s, %s)
        on conflict (installation_id, github_repository_id)
        do update set name = excluded.name, updated_at = now()
        returning id
        """,
        (installation_id, github_repository_id, name),
    ).fetchone()
    assert row is not None
    return uuid.UUID(str(row["id"]))


def approve_pairing(
    code: str,
    access: VerifiedInstallationAccess,
    repository_ids: Sequence[int],
) -> PairingApproved | PairingDenied:
    code_hash = hash_runner_credential(code)

    with connection() as conn, conn.transaction():
        pairing_row = conn.execute(
            """
            select id from pairing_codes
            where code_hash = %s and approved_at is null
              and created_at > now() - interval '10 minutes'
            for update
            """,
            (code_hash,),
        ).fetchone()
        if pairing_row is None:
            return PairingDenied(reason="invalid_or_expired_code")

        installation = conn.execute(
            "select revoked_at from installations where id = %s",
            (access.installation_id,),
        ).fetchone()
        if installation is None:
            return PairingDenied(reason="unknown_installation")
        if installation["revoked_at"] is not None:
            return PairingDenied(reason="revoked_installation")

        # A caller cannot request a repository their verified installation does not actually
        # cover: there is nothing to check that against except access.repositories itself, which
        # is exactly why VerifiedInstallationAccess carries the repository list, not just an id.
        for github_repository_id in repository_ids:
            if github_repository_id not in access.repositories:
                return PairingDenied(reason="repository_not_in_installation")

        repository_uuids = [
            _upsert_repository(
                conn,
                access.installation_id,
                github_repository_id,
                access.repositories[github_repository_id],
            )
            for github_repository_id in repository_ids
        ]

        conn.execute(
            """
            update pairing_codes
            set installation_id = %s, repository_ids = %s, approved_at = now()
            where id = %s
            """,
            (access.installation_id, repository_uuids, pairing_row["id"]),
        )

    return PairingApproved(
        installation_id=access.installation_id,
        repository_ids=tuple(repository_uuids),
    )


def exchange_pairing_code(
    code: str, proof: str
) -> RunnerCredential | PairingDenied | AssignmentRefused:
    code_hash = hash_runner_credential(code)
    # The verifier is hashed the same way the runner hashed it into the original challenge
    # (hash_runner_credential is a plain, deterministic SHA256, so this is just recomputing the
    # same value); the WHERE clause below only matches a row if this equals the stored challenge.
    proof_hash = hash_runner_credential(proof)

    runner_id: uuid.UUID | None = None
    credential: str | None = None

    with connection() as conn:
        try:
            with conn.transaction():
                # Not found, expired, already used, wrong verifier: there is only one reason.
                # Folding all four into one WHERE clause means telling them apart is not just
                # discouraged, it is not something this query can even do.
                pairing_row = conn.execute(
                    """
                    select id, device_name, repository_ids from pairing_codes
                    where code_hash = %s
                      and challenge = %s
                      and approved_at is not null
                      and exchanged_at is null
                      and created_at > now() - interval '10 minutes'
                    for update
                    """,
                    (code_hash, proof_hash),
                ).fetchone()
                if pairing_row is None:
                    return PairingDenied(reason="invalid_or_expired_code")

                credential = secrets.token_urlsafe(32)
                runner_id = register_runner(
                    conn,
                    str(pairing_row["device_name"]),
                    credential,
                    _INITIAL_RUNNER_CAPABILITIES,
                )

                for repository_id in pairing_row["repository_ids"] or []:
                    outcome = assign_repository_to_runner(conn, repository_id, runner_id)
                    if isinstance(outcome, AssignmentRefused):
                        # Raising forces this whole transaction, including the register_runner
                        # insert above, to roll back. A refused exchange must leave no runner row.
                        raise _ExchangeConflict(outcome)

                conn.execute(
                    "update pairing_codes set exchanged_at = now() where id = %s",
                    (pairing_row["id"],),
                )
        except _ExchangeConflict as conflict:
            return conflict.refused

    assert runner_id is not None
    assert credential is not None
    return RunnerCredential(runner_id=runner_id, credential=credential)
