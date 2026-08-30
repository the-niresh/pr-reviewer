"""Tests for the full-mode local Postgres + pgvector service (Runtime Task 7).

This is what makes retrieval possible on the user's machine. It starts only after Task 6's
select_runtime_mode grants full mode. Analysis-only must not be able to stand it up, because
analysis-only is the mode that never runs repository retrieval.

Password handling under test: a random password is generated on first start, stored in the
existing SecretStore (the same primitive as the runner credential and model keys), and never
placed on process argv or in docker-compose.runner.yml. The container reads it from
POSTGRES_PASSWORD_FILE. The connection URL is built in memory; status and logs must not carry
the password.

Imports of local_store.postgres stay inside test bodies so a missing module fails the test
instead of interrupting collection (same pattern as tests/test_runner_job_protocol.py).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from pr_reviewer.runner.modes import ModeDecision
from pr_reviewer.runner.secrets import FileSecretStore

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "pr_reviewer"
MIGRATIONS_DIR = SRC_ROOT / "local_store" / "postgres_migrations"
EXTENSIONS_MIGRATION = MIGRATIONS_DIR / "0000_extensions.sql"


def _full_mode() -> ModeDecision:
    return ModeDecision(
        requested_mode="full",
        granted_mode="full",
        retrieval_available=True,
        verification_available=True,
        forces_human_approval=False,
        downgraded=False,
        disabled_features=(),
        probe_failures=(),
    )


def _analysis_only_mode() -> ModeDecision:
    return ModeDecision(
        requested_mode="full",
        granted_mode="analysis_only",
        retrieval_available=False,
        verification_available=False,
        forces_human_approval=True,
        downgraded=True,
        disabled_features=("repository retrieval",),
        probe_failures=("docker CLI not found on PATH",),
    )


def test_extensions_migration_is_the_documented_0000_exception_and_enables_pgvector() -> None:
    assert EXTENSIONS_MIGRATION.is_file()
    names = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
    assert names[0] == "0000_extensions.sql"
    sql = EXTENSIONS_MIGRATION.read_text(encoding="utf-8").lower()
    assert "create extension" in sql
    assert "vector" in sql


def test_start_is_refused_when_select_runtime_mode_did_not_grant_full(
    tmp_path: Path,
) -> None:
    from pr_reviewer.local_store.postgres import LocalVectorStore, LocalVectorStoreError

    store = LocalVectorStore(
        secrets=FileSecretStore(tmp_path / "secrets"),
        mode=_analysis_only_mode(),
        work_directory=tmp_path,
    )
    with pytest.raises(LocalVectorStoreError):
        store.start()


class _RecordingResult:
    returncode = 0
    stdout = ""
    stderr = ""


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, args: Sequence[str], *, timeout: float) -> _RecordingResult:
        del timeout
        self.calls.append(tuple(args))
        return _RecordingResult()


def test_start_stores_a_generated_password_in_the_secret_store_not_on_argv(
    tmp_path: Path,
) -> None:
    from pr_reviewer.local_store.postgres import LOCAL_PGVECTOR_SECRET_NAME, LocalVectorStore

    secrets = FileSecretStore(tmp_path / "secrets")
    runner = _RecordingRunner()
    store = LocalVectorStore(
        secrets=secrets,
        mode=_full_mode(),
        work_directory=tmp_path,
        command_runner=runner,
    )
    status = store.start()

    password = secrets.get(LOCAL_PGVECTOR_SECRET_NAME)
    assert password is not None
    assert len(password) >= 24
    for argv in runner.calls:
        joined = " ".join(argv)
        assert password not in joined
        assert f"POSTGRES_PASSWORD={password}" not in joined
    assert status.bound_host == "127.0.0.1"
    assert "127.0.0.1" in status.url
    assert password not in repr(status)


def test_password_file_is_mode_0600_and_parent_is_0700(tmp_path: Path) -> None:
    from pr_reviewer.local_store.postgres import LocalVectorStore

    store = LocalVectorStore(
        secrets=FileSecretStore(tmp_path / "secrets"),
        mode=_full_mode(),
        work_directory=tmp_path,
        command_runner=_RecordingRunner(),
    )
    store.start()

    path = store.password_file_path
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_password_file_is_removed_on_stop_whether_or_not_data_is_preserved(
    tmp_path: Path,
) -> None:
    from pr_reviewer.local_store.postgres import LOCAL_PGVECTOR_SECRET_NAME, LocalVectorStore

    secrets = FileSecretStore(tmp_path / "secrets")
    store = LocalVectorStore(
        secrets=secrets,
        mode=_full_mode(),
        work_directory=tmp_path,
        command_runner=_RecordingRunner(),
    )

    store.start()
    path = store.password_file_path
    assert path.is_file()
    store.stop(preserve_data=True)
    assert not path.exists()
    assert secrets.get(LOCAL_PGVECTOR_SECRET_NAME) is not None

    store.start()
    path = store.password_file_path
    assert path.is_file()
    store.stop(preserve_data=False, confirm_delete=True)
    assert not path.exists()
    assert secrets.get(LOCAL_PGVECTOR_SECRET_NAME) is not None


def test_health_is_true_only_after_a_successful_start(tmp_path: Path) -> None:
    from pr_reviewer.local_store.postgres import LocalVectorStore

    store = LocalVectorStore(
        secrets=FileSecretStore(tmp_path / "secrets"),
        mode=_full_mode(),
        work_directory=tmp_path,
    )
    before = store.health()
    assert before.healthy is False
    assert before.running is False

    try:
        store.start()
        store.migrate()
        after = store.health()
        assert after.healthy is True
        assert after.running is True
    finally:
        store.stop(preserve_data=False, confirm_delete=True)


def test_migrate_makes_the_pgvector_extension_present(tmp_path: Path) -> None:
    from pr_reviewer.local_store.postgres import LocalVectorStore

    store = LocalVectorStore(
        secrets=FileSecretStore(tmp_path / "secrets"),
        mode=_full_mode(),
        work_directory=tmp_path,
    )
    try:
        store.start()
        store.migrate()
        assert store.extension_present("vector") is True
    finally:
        store.stop(preserve_data=False, confirm_delete=True)


def test_named_volume_survives_a_preserve_data_restart(tmp_path: Path) -> None:
    from pr_reviewer.local_store.postgres import LocalVectorStore

    secrets = FileSecretStore(tmp_path / "secrets")
    store = LocalVectorStore(
        secrets=secrets,
        mode=_full_mode(),
        work_directory=tmp_path,
    )
    restarted = LocalVectorStore(
        secrets=secrets,
        mode=_full_mode(),
        work_directory=tmp_path,
    )
    try:
        first = store.start()
        store.migrate()
        store.write_probe_row("restart-probe")
        store.stop(preserve_data=True)

        second = restarted.start()
        restarted.migrate()

        assert first.volume_name == second.volume_name
        assert first.volume_name != ""
        assert restarted.read_probe_row() == "restart-probe"
    finally:
        restarted.stop(preserve_data=False, confirm_delete=True)


def test_start_fails_clearly_on_a_port_collision(tmp_path: Path) -> None:
    from pr_reviewer.local_store.postgres import LocalVectorStore, LocalVectorStoreError

    occupant = LocalVectorStore(
        secrets=FileSecretStore(tmp_path / "secrets-a"),
        mode=_full_mode(),
        work_directory=tmp_path / "a",
    )
    try:
        first = occupant.start()
        colliding = LocalVectorStore(
            secrets=FileSecretStore(tmp_path / "secrets-b"),
            mode=_full_mode(),
            work_directory=tmp_path / "b",
            port=first.bound_port,
        )
        with pytest.raises(LocalVectorStoreError):
            colliding.start()
    finally:
        occupant.stop(preserve_data=False, confirm_delete=True)


def test_stop_preserves_the_volume_unless_delete_is_explicitly_confirmed(
    tmp_path: Path,
) -> None:
    from pr_reviewer.local_store.postgres import LocalVectorStore, LocalVectorStoreError

    store = LocalVectorStore(
        secrets=FileSecretStore(tmp_path / "secrets"),
        mode=_full_mode(),
        work_directory=tmp_path,
    )
    status = store.start()
    store.stop(preserve_data=True)
    assert store.volume_exists(status.volume_name) is True

    with pytest.raises(LocalVectorStoreError):
        store.stop(preserve_data=False)

    store.stop(preserve_data=False, confirm_delete=True)
    assert store.volume_exists(status.volume_name) is False


def test_postgres_module_never_imports_the_hosted_database_or_control_plane() -> None:
    source = (SRC_ROOT / "local_store" / "postgres.py").read_text(encoding="utf-8")
    assert "pr_reviewer.db" not in source
    assert "pr_reviewer.control_plane" not in source
    assert "pr_reviewer.cli" not in source


def test_postgres_module_never_chowns_the_password_file_or_volume() -> None:
    # A 0600 password file is readable in-container only if the service runs as the invoking
    # uid. os.chown to 999 fails on every non-root machine, and swallowing that error produces
    # a container auth failure that does not mention the file. This assertion is static because
    # the test process cannot drop privileges to prove the non-root path.
    source = (SRC_ROOT / "local_store" / "postgres.py").read_text(encoding="utf-8")
    assert "chown" not in source
