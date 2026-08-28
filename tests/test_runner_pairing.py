"""Tests for one-time runner pairing (Runtime Task 2).

Every denial reason here follows the rule in docs/phases/phase-2-security-design-gate.md, section
6: a reason must be computable from data the caller is already authorised to see. A caller
presenting a code and a verifier is not authorised to learn whether that code exists, is expired,
was already used, or belongs to someone else; telling those apart would let an attacker who is
guessing codes confirm a hit before they also have the matching verifier. So "code not found",
"code expired", "code already used", and "verifier does not match" all return the SAME reason.
Task 1 shipped exactly this kind of oracle once (an unscoped repository lookup); this file is
where the analogous bug for pairing would show up first.

Approval only ever upserts repository rows and records a selection against the pairing code; it
never creates a runner or a repository_assignments row. A pairing that is approved and then
abandoned (tab closed, runner host dies, code expires) must not leave any repository
permanently unclaimable. Only exchange, where a real credential and a real runner exist, creates
the runner and its assignments, in one transaction, so the one-active-assignment constraint on
repository_assignments is the single authoritative place that decides who holds a repository.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pr_reviewer.contracts.runner import VerifiedInstallationAccess
from pr_reviewer.db.client import connection

VerifiedAccessFactory = Callable[[int, int, dict[int, str] | None], VerifiedInstallationAccess]


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def backdate_pairing_code(code_hash: str, minutes_ago: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "update pairing_codes set created_at = now() - %s::interval where code_hash = %s",
            (f"{minutes_ago} minutes", code_hash),
        )


def fetch_pairing_code_row_for_challenge(challenge: str) -> dict[str, object]:
    with connection() as conn:
        row = conn.execute(
            "select * from pairing_codes where challenge = %s",
            (challenge,),
        ).fetchone()
    assert row is not None
    return dict(row)


def insert_installation(installation_id: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (installation_id, "acme"),
        )


def revoke_installation_row(installation_id: int) -> None:
    with connection() as conn, conn.transaction():
        conn.execute(
            "update installations set revoked_at = now() where id = %s", (installation_id,)
        )


def count_runners_named(device_name: str) -> int:
    with connection() as conn:
        row = conn.execute(
            "select count(*) as n from runners where device_name = %s",
            (device_name,),
        ).fetchone()
    assert row is not None
    return int(row["n"])


# The AST-based construction-site check for VerifiedInstallationAccess now lives in
# test_github_oauth.py (Runtime Task 2A): pairing.py stopped being the construction site once
# github_oauth.py grew the real, GitHub-verified one.


def test_pairing_code_is_stored_hashed_never_plaintext() -> None:
    from pr_reviewer.control_plane.pairing import create_pairing_code

    challenge = "test-challenge-value"
    challenge_result = create_pairing_code("laptop", challenge)

    row = fetch_pairing_code_row_for_challenge(challenge)
    assert challenge_result.code not in str(row.values())
    assert row["code_hash"] != challenge_result.code


def test_exchange_returns_a_working_credential_exactly_once(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import AuthenticatedRunner, RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )
    from pr_reviewer.control_plane.runner_auth import authenticate_runner

    installation_id = 5001
    insert_installation(installation_id)

    verifier = "correct-verifier"
    challenge_result = create_pairing_code("laptop", sha256_hex(verifier))
    access = make_verified_installation_access(42, installation_id, None)
    approve_pairing(challenge_result.code, access, [])

    result = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(result, RunnerCredential)
    assert result.credential

    authenticated = authenticate_runner(result.credential)
    assert isinstance(authenticated, AuthenticatedRunner)
    assert authenticated.runner_id == result.runner_id


def test_code_is_one_use_replay_after_exchange_is_denied(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingDenied, RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    installation_id = 5002
    insert_installation(installation_id)

    verifier = "correct-verifier"
    challenge_result = create_pairing_code("laptop", sha256_hex(verifier))
    access = make_verified_installation_access(42, installation_id, None)
    approve_pairing(challenge_result.code, access, [])

    first = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(first, RunnerCredential)

    replay = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(replay, PairingDenied)
    assert replay.reason == "invalid_or_expired_code"


def test_code_expires_after_ten_minutes(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingDenied
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    installation_id = 5003
    insert_installation(installation_id)

    verifier = "correct-verifier"
    challenge = sha256_hex(verifier)
    challenge_result = create_pairing_code("laptop", challenge)
    access = make_verified_installation_access(42, installation_id, None)
    approve_pairing(challenge_result.code, access, [])

    row = fetch_pairing_code_row_for_challenge(challenge)
    backdate_pairing_code(str(row["code_hash"]), minutes_ago=11)

    result = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(result, PairingDenied)
    assert result.reason == "invalid_or_expired_code"


def test_verifier_mismatch_is_denied_and_does_not_burn_the_code(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingDenied, RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    installation_id = 5004
    insert_installation(installation_id)

    verifier = "correct-verifier"
    challenge_result = create_pairing_code("laptop", sha256_hex(verifier))
    access = make_verified_installation_access(42, installation_id, None)
    approve_pairing(challenge_result.code, access, [])

    wrong_attempt = exchange_pairing_code(challenge_result.code, "wrong-verifier")
    assert isinstance(wrong_attempt, PairingDenied)
    assert wrong_attempt.reason == "invalid_or_expired_code"

    # The code must still be redeemable with the correct verifier: a wrong guess must not burn it.
    right_attempt = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(right_attempt, RunnerCredential)


def test_unknown_code_and_never_approved_code_return_the_same_denial_reason() -> None:
    from pr_reviewer.contracts.runner import PairingDenied
    from pr_reviewer.control_plane.pairing import create_pairing_code, exchange_pairing_code

    unknown = exchange_pairing_code("this-code-was-never-issued", "any-verifier")
    assert isinstance(unknown, PairingDenied)

    verifier = "correct-verifier"
    challenge_result = create_pairing_code("laptop", sha256_hex(verifier))
    never_approved = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(never_approved, PairingDenied)

    assert unknown.reason == never_approved.reason == "invalid_or_expired_code"


def test_approve_pairing_denied_for_unknown_installation(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingDenied
    from pr_reviewer.control_plane.pairing import approve_pairing, create_pairing_code

    challenge_result = create_pairing_code("laptop", sha256_hex("v"))
    access = make_verified_installation_access(42, 999999, None)

    result = approve_pairing(challenge_result.code, access, [])
    assert isinstance(result, PairingDenied)
    assert result.reason == "unknown_installation"


def test_approve_pairing_denied_for_revoked_installation(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingDenied
    from pr_reviewer.control_plane.pairing import approve_pairing, create_pairing_code

    installation_id = 5005
    insert_installation(installation_id)
    revoke_installation_row(installation_id)

    challenge_result = create_pairing_code("laptop", sha256_hex("v"))
    access = make_verified_installation_access(42, installation_id, None)

    result = approve_pairing(challenge_result.code, access, [])
    assert isinstance(result, PairingDenied)
    assert result.reason == "revoked_installation"


def test_approve_pairing_denies_a_repository_outside_the_verified_installation(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    # This is the tenancy attack VerifiedInstallationAccess exists to prevent: a caller cannot
    # ask approve_pairing to bind a repository their GitHub-verified installation does not
    # actually cover, because there is nothing to check that against except access.repositories
    # itself.
    from pr_reviewer.contracts.runner import PairingDenied
    from pr_reviewer.control_plane.pairing import approve_pairing, create_pairing_code

    installation_id = 5006
    insert_installation(installation_id)

    challenge_result = create_pairing_code("laptop", sha256_hex("v"))
    access = make_verified_installation_access(42, installation_id, {111: "in-scope"})

    result = approve_pairing(challenge_result.code, access, [999])
    assert isinstance(result, PairingDenied)
    assert result.reason == "repository_not_in_installation"


def test_approve_pairing_registers_a_repository_that_does_not_exist_yet(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingApproved
    from pr_reviewer.control_plane.pairing import approve_pairing, create_pairing_code

    installation_id = 5007
    insert_installation(installation_id)

    challenge_result = create_pairing_code("laptop", sha256_hex("v"))
    access = make_verified_installation_access(42, installation_id, {778899: "widgets"})

    result = approve_pairing(challenge_result.code, access, [778899])
    assert isinstance(result, PairingApproved)
    assert len(result.repository_ids) == 1

    with connection() as conn:
        row = conn.execute(
            "select id, name from repositories"
            " where installation_id = %s and github_repository_id = %s",
            (installation_id, 778899),
        ).fetchone()
    assert row is not None
    assert row["name"] == "widgets"
    assert uuid.UUID(str(row["id"])) == result.repository_ids[0]


def test_exchange_refuses_a_repository_already_assigned_to_another_runner(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    # Approval never creates a runner or an assignment, so two pairings can both be approved for
    # the same repository without either approval seeing a conflict. The unique constraint on
    # repository_assignments.repository_id is the only authoritative check, and it only exists
    # once exchange tries to create a real assignment for a real runner.
    from pr_reviewer.contracts.runner import AssignmentRefused, RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    installation_id = 5008
    insert_installation(installation_id)
    access = make_verified_installation_access(42, installation_id, {778900: "widgets"})

    first_challenge = create_pairing_code("laptop-one", sha256_hex("v1"))
    approve_pairing(first_challenge.code, access, [778900])
    first_result = exchange_pairing_code(first_challenge.code, "v1")
    assert isinstance(first_result, RunnerCredential)

    second_challenge = create_pairing_code("laptop-two", sha256_hex("v2"))
    second_approval = approve_pairing(second_challenge.code, access, [778900])
    assert not isinstance(second_approval, AssignmentRefused)

    second_result = exchange_pairing_code(second_challenge.code, "v2")
    assert isinstance(second_result, AssignmentRefused)
    assert second_result.active_runner.runner_id == first_result.runner_id

    # The refused exchange must not leave an orphan, credential-less runner behind.
    assert count_runners_named("laptop-two") == 0


def test_never_exchanged_pairing_leaves_its_repository_claimable_by_a_later_runner(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    installation_id = 5009
    insert_installation(installation_id)
    access = make_verified_installation_access(42, installation_id, {778901: "widgets"})

    abandoned_challenge = create_pairing_code("abandoned-laptop", sha256_hex("v1"))
    approve_pairing(abandoned_challenge.code, access, [778901])
    # abandoned_challenge is deliberately never exchanged: tab closed, host died, code expires.

    later_challenge = create_pairing_code("later-laptop", sha256_hex("v2"))
    approve_pairing(later_challenge.code, access, [778901])
    later_result = exchange_pairing_code(later_challenge.code, "v2")
    assert isinstance(later_result, RunnerCredential)

    with connection() as conn:
        row = conn.execute(
            "select runner_id from repository_assignments ra join repositories r "
            "on r.id = ra.repository_id "
            "where r.installation_id = %s and r.github_repository_id = %s",
            (installation_id, 778901),
        ).fetchone()
    assert row is not None
    assert uuid.UUID(str(row["runner_id"])) == later_result.runner_id


def test_concurrent_exchange_of_the_same_code_exactly_one_wins(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingDenied, RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    installation_id = 5010
    insert_installation(installation_id)

    verifier = "correct-verifier"
    challenge_result = create_pairing_code("laptop", sha256_hex(verifier))
    access = make_verified_installation_access(42, installation_id, None)
    approve_pairing(challenge_result.code, access, [])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(exchange_pairing_code, challenge_result.code, verifier) for _ in range(2)
        ]
        results = [future.result() for future in futures]

    credentials = [r for r in results if isinstance(r, RunnerCredential)]
    denials = [r for r in results if isinstance(r, PairingDenied)]
    assert len(credentials) == 1, f"expected exactly one winner, got: {results}"
    assert len(denials) == 1
    assert denials[0].reason == "invalid_or_expired_code"
