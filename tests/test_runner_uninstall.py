"""Tests for runner uninstall (Runtime Task 9).

Uninstall preserves local reviews and container volumes by default. Removing model keys, runner
credentials, SQLite data, or pgvector volumes requires explicit confirmation, matching
LocalVectorStore.stop(preserve_data=False, confirm_delete=True) from Task 7. Commands live in
runner/cli/, not the operator cli/ package. Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pr_reviewer.runner.secrets import FileSecretStore


class RecordingVectorStore:
    def __init__(self) -> None:
        self.stops: list[tuple[bool, bool]] = []
        self.volume_present = True

    def stop(self, preserve_data: bool, *, confirm_delete: bool = False) -> None:
        if not preserve_data and not confirm_delete:
            raise RuntimeError(
                "refusing to delete the pgvector volume without confirm_delete=True"
            )
        self.stops.append((preserve_data, confirm_delete))
        if not preserve_data:
            self.volume_present = False


def test_uninstall_preserves_local_reviews_and_volumes_by_default(tmp_path: Path) -> None:
    from pr_reviewer.runner.cli.uninstall import uninstall_runner

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sqlite = data_dir / "local_state.sqlite3"
    sqlite.write_bytes(b"reviews")
    secrets = FileSecretStore(tmp_path / "secrets")
    secrets.set("model_key", "sk-keep")
    secrets.set("runner_credential", "cred-keep")
    volumes = RecordingVectorStore()

    uninstall_runner(
        data_dir=data_dir,
        secrets=secrets,
        vector_store=volumes,
        preserve_data=True,
    )

    assert sqlite.is_file()
    assert secrets.get("model_key") == "sk-keep"
    assert secrets.get("runner_credential") == "cred-keep"
    assert volumes.stops == [(True, False)]
    assert volumes.volume_present is True


def test_uninstall_refuses_to_delete_without_confirm_delete(tmp_path: Path) -> None:
    from pr_reviewer.runner.cli.uninstall import UninstallError, uninstall_runner

    secrets = FileSecretStore(tmp_path / "secrets")
    secrets.set("model_key", "sk-keep")
    with pytest.raises(UninstallError, match="confirm_delete"):
        uninstall_runner(
            data_dir=tmp_path / "data",
            secrets=secrets,
            vector_store=RecordingVectorStore(),
            preserve_data=False,
            confirm_delete=False,
        )
    assert secrets.get("model_key") == "sk-keep"


def test_uninstall_deletes_secrets_sqlite_and_volumes_only_when_confirmed(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.cli.uninstall import uninstall_runner

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sqlite = data_dir / "local_state.sqlite3"
    sqlite.write_bytes(b"reviews")
    secrets = FileSecretStore(tmp_path / "secrets")
    secrets.set("model_key", "sk-delete")
    secrets.set("runner_credential", "cred-delete")
    secrets.set("local_session_secret", "session-delete")
    volumes = RecordingVectorStore()

    uninstall_runner(
        data_dir=data_dir,
        secrets=secrets,
        vector_store=volumes,
        preserve_data=False,
        confirm_delete=True,
    )

    assert not sqlite.exists()
    assert secrets.get("model_key") is None
    assert secrets.get("runner_credential") is None
    assert secrets.get("local_session_secret") is None
    assert volumes.stops == [(False, True)]
    assert volumes.volume_present is False


def test_reviewer_cli_routes_update_and_uninstall_through_runner_cli_not_operator_cli() -> None:
    from pathlib import Path as PathType

    import pr_reviewer.reviewer as reviewer_mod

    source = PathType(reviewer_mod.__file__).read_text(encoding="utf-8")
    assert "pr_reviewer.runner.cli" in source
    assert "update" in reviewer_mod._USAGE
    assert "uninstall" in reviewer_mod._USAGE
    assert "pr_reviewer.cli.update" not in source
    assert "pr_reviewer.cli.uninstall" not in source
    assert "pr_reviewer.cli.main" not in source


def test_reviewer_uninstall_without_confirm_delete_does_not_remove_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pr_reviewer.reviewer import main as reviewer_main

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sqlite = data_dir / "local_state.sqlite3"
    sqlite.write_bytes(b"reviews")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    code = reviewer_main(["uninstall", "--delete-data"])
    captured = capsys.readouterr()

    assert code != 0
    assert "confirm" in captured.err.lower()
    assert sqlite.is_file()
