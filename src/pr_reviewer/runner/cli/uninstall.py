"""Uninstall the local runner (Runtime Task 9).

Preserves local reviews and container volumes by default. Removing model keys, runner
credentials, SQLite data, or pgvector volumes requires the same confirmation shape as
LocalVectorStore.stop(preserve_data=False, confirm_delete=True).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pr_reviewer.runner.secrets import SecretStore, get_secret_store

_SECRET_NAMES = (
    "model_key",
    "runner_credential",
    "local_session_secret",
    "local_pgvector_password",
)


class UninstallError(RuntimeError):
    """Refused to delete user data without confirm_delete=True."""


class VectorStoreStop(Protocol):
    def stop(self, preserve_data: bool, *, confirm_delete: bool = False) -> None: ...


def uninstall_runner(
    *,
    data_dir: Path,
    secrets: SecretStore,
    vector_store: VectorStoreStop | None = None,
    preserve_data: bool = True,
    confirm_delete: bool = False,
) -> None:
    if not preserve_data and not confirm_delete:
        raise UninstallError("refusing to delete runner data without confirm_delete=True")
    if vector_store is not None:
        vector_store.stop(preserve_data, confirm_delete=confirm_delete)
    if preserve_data:
        return
    (data_dir / "local_state.sqlite3").unlink(missing_ok=True)
    for name in _SECRET_NAMES:
        secrets.delete(name)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="reviewer uninstall",
        description="Remove the local runner while preserving local data by default.",
        epilog=(
            "Output: no output on success. Refusals are printed to stderr.\n\n"
            "exit codes:\n"
            "  0  uninstall completed\n"
            "  1  uninstall was refused or failed\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--delete-data", action="store_true", help="Delete local runner data.")
    parser.add_argument(
        "--confirm-delete",
        action="store_true",
        help="Required with --delete-data.",
    )
    parsed = parser.parse_args(args)
    from pr_reviewer.runner.cli.service import _data_dir

    data_dir = _data_dir()
    secrets = get_secret_store(file_fallback_directory=data_dir / "secrets")
    try:
        uninstall_runner(
            data_dir=data_dir,
            secrets=secrets,
            preserve_data=not parsed.delete_data,
            confirm_delete=parsed.confirm_delete,
        )
    except UninstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
