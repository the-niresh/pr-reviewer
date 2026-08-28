"""Tests for one-time runner pairing (Runtime Task 2).

Every denial reason here follows the rule in docs/phases/phase-2-security-design-gate.md, section
6: a reason must be computable from data the caller is already authorised to see. A caller
presenting a code and a verifier is not authorised to learn whether that code exists, is expired,
was already used, or belongs to someone else; telling those apart would let an attacker who is
guessing codes confirm a hit before they also have the matching verifier. So "code not found",
"code expired", "code already used", and "verifier does not match" all return the SAME reason.
Task 1 shipped exactly this kind of oracle once (an unscoped repository lookup); this file is
where the analogous bug for pairing would show up first.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pr_reviewer.db.client import connection

VerifiedAccessFactory = Callable[[int, int], object]

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"


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
        conn.execute("update installations set revoked_at = now() where id = %s", (installation_id,))


def test_verified_installation_access_has_exactly_one_construction_site_in_src() -> None:
    # Same shape as EXPECTED_EXISTING_PACKAGES in test_package_boundaries.py: the day a second
    # module constructs VerifiedInstallationAccess directly instead of going through the one
    # verified path, this fails. Scoped to src/ only, so the test-only builder in tests/conftest.py
    # does not count.
    construction_pattern = re.compile(r"\bVerifiedInstallationAccess\(")
    sites: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if construction_pattern.search(text):
            sites.append(str(path.relative_to(SRC_ROOT.parent.parent)))

    assert sites == ["src/pr_reviewer/control_plane/pairing.py"], (
        "VerifiedInstallationAccess must be constructed in exactly "
        f"src/pr_reviewer/control_plane/pairing.py, found: {sites}"
    )


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
    from pr_reviewer.contracts.runner import RunnerCredential
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
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)
    approve_pairing(challenge_result.code, access, [])

    result = exchange_pairing_code(challenge_result.code, verifier)
    assert isinstance(result, RunnerCredential)
    assert result.credential

    authenticated = authenticate_runner(result.credential)
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
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)
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
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)
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
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)
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
    access = make_verified_installation_access(github_user_id=42, installation_id=999999)

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
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)

    result = approve_pairing(challenge_result.code, access, [])
    assert isinstance(result, PairingDenied)
    assert result.reason == "revoked_installation"


def test_approve_pairing_registers_a_repository_that_does_not_exist_yet(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import RepositorySelection, RunnerRegistration
    from pr_reviewer.control_plane.pairing import approve_pairing, create_pairing_code

    installation_id = 5006
    insert_installation(installation_id)

    challenge_result = create_pairing_code("laptop", sha256_hex("v"))
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)
    selection = RepositorySelection(github_repository_id=778899, name="widgets")

    result = approve_pairing(challenge_result.code, access, [selection])
    assert isinstance(result, RunnerRegistration)
    assert len(result.repository_ids) == 1

    with connection() as conn:
        row = conn.execute(
            "select id from repositories where installation_id = %s and github_repository_id = %s",
            (installation_id, 778899),
        ).fetchone()
    assert row is not None
    assert uuid.UUID(str(row["id"])) == result.repository_ids[0]


def test_approve_pairing_refuses_a_repository_already_assigned_to_another_runner(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import (
        AssignmentRefused,
        RepositorySelection,
        RunnerRegistration,
    )
    from pr_reviewer.control_plane.pairing import approve_pairing, create_pairing_code

    installation_id = 5007
    insert_installation(installation_id)

    selection = RepositorySelection(github_repository_id=778900, name="widgets")
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)

    first_challenge = create_pairing_code("laptop-one", sha256_hex("v1"))
    first_result = approve_pairing(first_challenge.code, access, [selection])
    assert isinstance(first_result, RunnerRegistration)

    second_challenge = create_pairing_code("laptop-two", sha256_hex("v2"))
    second_result = approve_pairing(second_challenge.code, access, [selection])
    assert isinstance(second_result, AssignmentRefused)
    assert second_result.active_runner.runner_id == first_result.runner_id


def test_concurrent_exchange_of_the_same_code_exactly_one_wins(
    make_verified_installation_access: VerifiedAccessFactory,
) -> None:
    from pr_reviewer.contracts.runner import PairingDenied, RunnerCredential
    from pr_reviewer.control_plane.pairing import (
        approve_pairing,
        create_pairing_code,
        exchange_pairing_code,
    )

    installation_id = 5008
    insert_installation(installation_id)

    verifier = "correct-verifier"
    challenge_result = create_pairing_code("laptop", sha256_hex(verifier))
    access = make_verified_installation_access(github_user_id=42, installation_id=installation_id)
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
