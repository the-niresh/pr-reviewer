"""Versioned runner updates with checksum verification and rollback (Runtime Task 9).

The incoming artifact is hashed before any installed file is replaced. The prior version is
copied aside first so a half-written replace can be undone. An update that cannot roll back is
worse than no update.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class UpdateError(RuntimeError):
    """The incoming artifact failed its checksum, or replace failed after rollback."""


@dataclass(frozen=True)
class UpdateResult:
    version: str
    prior_path: Path


def apply_update(
    *,
    install_path: Path,
    artifact_path: Path,
    expected_sha256: str,
    version: str,
) -> UpdateResult:
    payload = artifact_path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise UpdateError(
            f"checksum mismatch: expected {expected_sha256}, got {actual}"
        )

    install_path.parent.mkdir(parents=True, exist_ok=True)
    prior_path = install_path.with_name(f"{install_path.name}.prior")
    if install_path.is_file():
        prior_path.write_bytes(install_path.read_bytes())

    staging = install_path.with_name(f"{install_path.name}.new")
    staging.write_bytes(payload)
    try:
        staging.replace(install_path)
    except OSError as exc:
        staging.unlink(missing_ok=True)
        if prior_path.is_file():
            install_path.write_bytes(prior_path.read_bytes())
        raise UpdateError(
            "failed to replace installed file; rolled back to the prior version"
        ) from exc
    return UpdateResult(version=version, prior_path=prior_path)
