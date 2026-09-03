"""Tests for the hosted identity and data-boundary schema (Runtime Task 1).

Identity is the numeric GitHub installation ID and repository ID, never the display name, and
never inferred by joining on anything else. These tests exist to make three things fail loudly if
they ever regress: a rename moving data, a repository transfer leaking the old installation's rows
into the new one, and a second active assignment for the same repository slipping past the
database.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from pr_reviewer.contracts.runner import (
    AssignmentGranted,
    AssignmentRefused,
    AuthorizationDenied,
    RepositoryAuthorization,
    RunnerCapabilities,
)
from pr_reviewer.control_plane.app import app as control_plane_app
from pr_reviewer.control_plane.repository_policy import (
    assign_repository_to_runner,
    authorize_repository,
    hash_runner_credential,
    register_installation,
    register_repository,
    register_runner,
    rename_repository,
    revoke_installation,
    revoke_runner,
)
from pr_reviewer.db.client import connection
from pr_reviewer.web.app import app as web_app

ANALYSIS_ONLY_CAPABILITIES = RunnerCapabilities(
    mode="analysis_only",
    docker_available=False,
    retrieval_available=False,
    verification_available=False,
    platform="linux",
    version="0.1.0",
)


def make_installation(installation_id: int, account_login: str = "acme") -> int:
    register_installation(installation_id, account_login)
    return installation_id


def make_repository(
    installation_id: int, github_repository_id: int, name: str = "widgets"
) -> uuid.UUID:
    return register_repository(installation_id, github_repository_id, name)


def make_runner(device_name: str = "laptop", credential: str = "s3cr3t") -> uuid.UUID:
    with connection() as conn, conn.transaction():
        return register_runner(conn, device_name, credential, ANALYSIS_ONLY_CAPABILITIES)


def make_assignment(
    repository_id: uuid.UUID, runner_id: uuid.UUID
) -> AssignmentGranted | AssignmentRefused:
    with connection() as conn, conn.transaction():
        return assign_repository_to_runner(conn, repository_id, runner_id)


# --- identity is the numeric ID, a name is a label ---------------------------------------------


def test_repository_identity_is_the_numeric_github_id_not_the_name() -> None:
    make_installation(1001)
    repository_row_id = make_repository(1001, github_repository_id=555, name="widgets")
    runner_id = make_runner()
    make_assignment(repository_row_id, runner_id)

    before = authorize_repository(1001, 555, runner_id)
    rename_repository(repository_row_id, "widgets-renamed")
    after = authorize_repository(1001, 555, runner_id)

    assert isinstance(before, RepositoryAuthorization)
    assert isinstance(after, RepositoryAuthorization)
    assert before == after


def test_renaming_a_repository_does_not_move_orphan_or_expose_data() -> None:
    make_installation(1002)
    repository_row_id = make_repository(1002, github_repository_id=556, name="original-name")
    runner_id = make_runner(device_name="rename-test-runner")
    make_assignment(repository_row_id, runner_id)

    rename_repository(repository_row_id, "renamed")

    with connection() as conn:
        row = conn.execute(
            "select id, installation_id, github_repository_id, name from repositories"
            " where id = %s",
            (str(repository_row_id),),
        ).fetchone()

    assert row is not None
    assert str(row["id"]) == str(repository_row_id)
    assert row["installation_id"] == 1002
    assert row["github_repository_id"] == 556
    assert row["name"] == "renamed"

    result = authorize_repository(1002, 556, runner_id)
    assert isinstance(result, RepositoryAuthorization)


# --- duplicate installations --------------------------------------------------------------------


def test_duplicate_installation_id_is_rejected_by_the_database() -> None:
    make_installation(2001)

    with pytest.raises(psycopg.errors.UniqueViolation), connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (2001, "acme-again"),
        )


# --- repository transfer between installations --------------------------------------------------


def test_repository_transfer_does_not_carry_data_to_the_new_installation() -> None:
    old_installation_id = 3001
    new_installation_id = 3002
    github_repository_id = 777

    make_installation(old_installation_id)
    old_repository_row_id = make_repository(old_installation_id, github_repository_id, "moved-repo")
    runner_id = make_runner(device_name="transfer-test-runner")
    make_assignment(old_repository_row_id, runner_id)

    before_transfer = authorize_repository(old_installation_id, github_repository_id, runner_id)
    assert isinstance(before_transfer, RepositoryAuthorization)

    # GitHub reports a new installation for the same numeric repository ID. Nothing about the old
    # installation's data is reachable from the new one at any point in this sequence.
    denied_before_registration = authorize_repository(
        new_installation_id, github_repository_id, runner_id
    )
    assert isinstance(denied_before_registration, AuthorizationDenied)
    assert denied_before_registration.reason == "unknown_installation"

    make_installation(new_installation_id)
    # A row for this numeric repository ID already exists, just under the old installation. This is
    # deliberately indistinguishable from a repository nobody has ever registered: see
    # test_cross_installation_access_is_denied_for_a_repository_registered_elsewhere below, where
    # the identical database state produces the identical reason for the identical cause.
    denied_unregistered_repo = authorize_repository(
        new_installation_id, github_repository_id, runner_id
    )
    assert isinstance(denied_unregistered_repo, AuthorizationDenied)
    assert denied_unregistered_repo.reason == "unknown_repository"

    new_repository_row_id = make_repository(
        new_installation_id, github_repository_id, "moved-repo"
    )
    denied_no_assignment = authorize_repository(
        new_installation_id, github_repository_id, runner_id
    )
    assert isinstance(denied_no_assignment, AuthorizationDenied)
    assert denied_no_assignment.reason == "runner_not_assigned_to_repository"

    assert new_repository_row_id != old_repository_row_id

    # The old installation's assignment is untouched by any of the above.
    still_valid = authorize_repository(old_installation_id, github_repository_id, runner_id)
    assert isinstance(still_valid, RepositoryAuthorization)


# --- cross-installation and cross-repository access ----------------------------------------------


def test_cross_installation_access_is_denied_for_a_repository_registered_elsewhere() -> None:
    make_installation(4001)
    make_installation(4002)
    repository_row_id = make_repository(4001, github_repository_id=888, name="repo-a")
    runner_id = make_runner(device_name="cross-install-runner")
    make_assignment(repository_row_id, runner_id)

    result = authorize_repository(4002, 888, runner_id)

    # Indistinguishable from "888 has never been registered by anyone", on purpose. Telling
    # installation 4002 that 888 exists, just under some other installation, would be a
    # cross-tenant leak through the denial reason alone, even though no row content is returned.
    assert isinstance(result, AuthorizationDenied)
    assert result.reason == "unknown_repository"


def test_unknown_repository_id_is_denied() -> None:
    make_installation(4101)
    runner_id = make_runner(device_name="unknown-repo-runner")

    result = authorize_repository(4101, 999999, runner_id)

    assert isinstance(result, AuthorizationDenied)
    assert result.reason == "unknown_repository"


def test_unknown_installation_id_is_denied() -> None:
    runner_id = make_runner(device_name="unknown-install-runner")

    result = authorize_repository(9999999, 1, runner_id)

    assert isinstance(result, AuthorizationDenied)
    assert result.reason == "unknown_installation"


def test_runner_not_assigned_to_any_repository_is_denied() -> None:
    make_installation(4201)
    make_repository(4201, github_repository_id=901, name="repo-unassigned")
    runner_id = make_runner(device_name="unassigned-runner")

    result = authorize_repository(4201, 901, runner_id)

    assert isinstance(result, AuthorizationDenied)
    assert result.reason == "runner_not_assigned_to_repository"


def test_runner_assigned_to_a_different_repository_cannot_reach_this_one() -> None:
    make_installation(4301)
    repository_a = make_repository(4301, github_repository_id=902, name="repo-a")
    repository_b = make_repository(4301, github_repository_id=903, name="repo-b")
    runner_id = make_runner(device_name="scoped-runner")
    make_assignment(repository_a, runner_id)
    del repository_b

    result = authorize_repository(4301, 903, runner_id)

    assert isinstance(result, AuthorizationDenied)
    assert result.reason == "runner_not_assigned_to_repository"


# --- one active assignment per repository --------------------------------------------------------


def test_second_active_assignment_for_same_repository_rejected_by_database_constraint() -> None:
    make_installation(5001)
    repository_row_id = make_repository(5001, github_repository_id=1001, name="constraint-repo")
    runner_a = make_runner(device_name="runner-a")
    runner_b = make_runner(device_name="runner-b")

    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into repository_assignments (repository_id, runner_id) values (%s, %s)",
            (str(repository_row_id), str(runner_a)),
        )

    with pytest.raises(psycopg.errors.UniqueViolation), connection() as conn, conn.transaction():
        conn.execute(
            "insert into repository_assignments (repository_id, runner_id) values (%s, %s)",
            (str(repository_row_id), str(runner_b)),
        )


def test_second_runner_pairing_an_assigned_repository_is_refused_not_auto_revoked() -> None:
    make_installation(5101)
    repository_row_id = make_repository(5101, github_repository_id=1101, name="pairing-repo")
    first_runner_id = make_runner(device_name="first-laptop")
    second_runner_id = make_runner(device_name="second-laptop")

    first_result = make_assignment(repository_row_id, first_runner_id)
    assert isinstance(first_result, AssignmentGranted)

    second_result = make_assignment(repository_row_id, second_runner_id)

    assert isinstance(second_result, AssignmentRefused)
    assert second_result.active_runner.runner_id == first_runner_id
    assert second_result.active_runner.device_name == "first-laptop"

    # The refusal did not touch the first runner's assignment, and the second runner still has none.
    still_authorized = authorize_repository(5101, 1101, first_runner_id)
    assert isinstance(still_authorized, RepositoryAuthorization)
    second_still_denied = authorize_repository(5101, 1101, second_runner_id)
    assert isinstance(second_still_denied, AuthorizationDenied)
    assert second_still_denied.reason == "runner_not_assigned_to_repository"


# --- runner credentials, capabilities, and revocation --------------------------------------------


def test_runner_credential_is_stored_only_as_a_hash() -> None:
    plaintext_credential = "correct-horse-battery-staple"
    runner_id = make_runner(device_name="hash-test-runner", credential=plaintext_credential)

    with connection() as conn:
        row = conn.execute(
            "select credential_hash from runners where id = %s",
            (str(runner_id),),
        ).fetchone()

    assert row is not None
    assert row["credential_hash"] != plaintext_credential
    assert plaintext_credential not in row["credential_hash"]
    assert row["credential_hash"] == hash_runner_credential(plaintext_credential)


def test_runner_capabilities_and_lifecycle_fields_are_recorded() -> None:
    capabilities = RunnerCapabilities(
        mode="full",
        docker_available=True,
        retrieval_available=True,
        verification_available=True,
        platform="darwin",
        version="1.2.3",
    )
    with connection() as conn, conn.transaction():
        runner_id = register_runner(conn, "full-mode-runner", "another-credential", capabilities)

    with connection() as conn:
        row = conn.execute(
            """
            select mode, docker_available, retrieval_available, verification_available,
                   platform, version, revoked_at
            from runners where id = %s
            """,
            (str(runner_id),),
        ).fetchone()

    assert row is not None
    assert row["mode"] == "full"
    assert row["docker_available"] is True
    assert row["retrieval_available"] is True
    assert row["verification_available"] is True
    assert row["platform"] == "darwin"
    assert row["version"] == "1.2.3"
    assert row["revoked_at"] is None


def test_runner_revocation_is_a_timestamp_not_a_delete() -> None:
    runner_id = make_runner(device_name="revoke-test-runner")

    revoke_runner(runner_id)

    with connection() as conn:
        row = conn.execute(
            "select id, revoked_at from runners where id = %s",
            (str(runner_id),),
        ).fetchone()

    assert row is not None, "revocation must not delete the row, this project is soft-delete only"
    assert row["revoked_at"] is not None


def test_revoked_runner_fails_authorization() -> None:
    make_installation(6001)
    repository_row_id = make_repository(6001, github_repository_id=1201, name="revoked-runner-repo")
    runner_id = make_runner(device_name="soon-revoked-runner")
    make_assignment(repository_row_id, runner_id)
    assert isinstance(authorize_repository(6001, 1201, runner_id), RepositoryAuthorization)

    revoke_runner(runner_id)

    result = authorize_repository(6001, 1201, runner_id)
    assert isinstance(result, AuthorizationDenied)
    assert result.reason == "revoked_runner"


def test_revoking_a_runner_frees_its_repository_for_reassignment() -> None:
    # Regression: repository_assignments carries unique(repository_id) -- one runner per
    # repository, ever, enforced by the schema. revoke_runner used to only stamp
    # revoked_at, leaving that row in place, so every repository a runner ever held
    # stayed permanently unassignable: exchange_pairing_code's own 409 detail already
    # says "revoke it there first", which was not actually possible before this fix.
    from pr_reviewer.contracts.runner import AssignmentGranted

    make_installation(6201)
    repository_row_id = make_repository(6201, github_repository_id=1401, name="freed-repo")
    old_runner_id = make_runner(device_name="old-runner", credential="old-cred")
    assert isinstance(make_assignment(repository_row_id, old_runner_id), AssignmentGranted)

    revoke_runner(old_runner_id)

    new_runner_id = make_runner(device_name="new-runner", credential="new-cred")
    result = make_assignment(repository_row_id, new_runner_id)
    assert isinstance(result, AssignmentGranted)


def test_revoked_installation_fails_authorization() -> None:
    make_installation(6101)
    repository_row_id = make_repository(
        6101, github_repository_id=1301, name="revoked-install-repo"
    )
    runner_id = make_runner(device_name="revoked-install-runner")
    make_assignment(repository_row_id, runner_id)
    assert isinstance(authorize_repository(6101, 1301, runner_id), RepositoryAuthorization)

    revoke_installation(6101)

    result = authorize_repository(6101, 1301, runner_id)
    assert isinstance(result, AuthorizationDenied)
    assert result.reason == "revoked_installation"


def test_installation_revocation_is_a_timestamp_not_a_delete() -> None:
    make_installation(6201)

    revoke_installation(6201)

    with connection() as conn:
        row = conn.execute(
            "select id, revoked_at from installations where id = %s",
            (6201,),
        ).fetchone()

    assert row is not None
    assert row["revoked_at"] is not None


# --- web/app.py split -----------------------------------------------------------------------------


def test_hosted_routes_live_in_control_plane_app_and_web_app_still_serves_the_webhook() -> None:
    # web/app.py must not fork the webhook into a second implementation. It has to be the same
    # FastAPI app control_plane/app.py composes, so the existing webhook tests in test_webhook.py
    # keep exercising the real thing without being rewritten by this task.
    assert web_app is control_plane_app
