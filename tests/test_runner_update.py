"""Tests for versioned runner updates with checksums and rollback (Runtime Task 9).

An update that half-writes and cannot roll back is worse than no update. Checksums are verified
before any installed file is replaced, and the prior version is kept so rollback has somewhere
to go. Imports of runner.update stay inside test bodies so a missing module fails the test
instead of interrupting collection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_update_refuses_to_replace_a_file_when_the_checksum_does_not_match(
    tmp_path: Path,
) -> None:
    from pr_reviewer.runner.update import UpdateError, apply_update

    current = tmp_path / "current" / "reviewer"
    current.parent.mkdir()
    current.write_bytes(b"installed-v1")
    incoming = tmp_path / "incoming.bin"
    incoming.write_bytes(b"installed-v2")

    with pytest.raises(UpdateError, match="(?i)checksum"):
        apply_update(
            install_path=current,
            artifact_path=incoming,
            expected_sha256=_sha256(b"not-the-bytes"),
            version="2.0.0",
        )

    assert current.read_bytes() == b"installed-v1"


def test_update_keeps_the_prior_version_for_rollback(tmp_path: Path) -> None:
    from pr_reviewer.runner.update import apply_update

    current = tmp_path / "current" / "reviewer"
    current.parent.mkdir()
    current.write_bytes(b"installed-v1")
    incoming = tmp_path / "incoming.bin"
    payload = b"installed-v2"
    incoming.write_bytes(payload)

    result = apply_update(
        install_path=current,
        artifact_path=incoming,
        expected_sha256=_sha256(payload),
        version="2.0.0",
    )

    assert current.read_bytes() == payload
    assert result.prior_path.is_file()
    assert result.prior_path.read_bytes() == b"installed-v1"
    assert result.version == "2.0.0"


def test_failed_replace_rolls_back_to_the_prior_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pr_reviewer.runner.update import UpdateError, apply_update

    current = tmp_path / "current" / "reviewer"
    current.parent.mkdir()
    current.write_bytes(b"installed-v1")
    incoming = tmp_path / "incoming.bin"
    payload = b"installed-v2-partial"
    incoming.write_bytes(payload)

    real_replace = Path.replace

    def boom(self: Path, target: Path) -> Path:
        if self.name.endswith(".new"):
            raise OSError("disk full")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", boom)

    with pytest.raises(UpdateError):
        apply_update(
            install_path=current,
            artifact_path=incoming,
            expected_sha256=_sha256(payload),
            version="2.0.0",
        )

    assert current.read_bytes() == b"installed-v1"
