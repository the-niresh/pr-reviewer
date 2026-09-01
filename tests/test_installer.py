"""Failing tests for the versioned installer and setup wizard (master Task 25)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from pr_reviewer.runner.secrets import FileSecretStore

REPO = Path(__file__).resolve().parent.parent
HOSTED_FLAGS = ("--neon", "--webhook-secret", "--github-app-private-key", "--pat", "--model-key")


def test_setup_stores_model_key_from_hidden_input_not_argv(tmp_path: Path) -> None:
    from pr_reviewer.cli.main import run_setup

    secrets = FileSecretStore(tmp_path / "secrets")
    key = "sk-must-not-appear-in-argv"
    argv = ["setup", "--hosted-origin", "https://control.example.test"]
    result = run_setup(
        hosted_origin="https://control.example.test",
        secrets=secrets,
        read_secret=lambda _prompt: key,
        argv=argv,
    )
    assert result == 0
    assert secrets.get("model_key") == key
    assert key not in argv
    for flag in HOSTED_FLAGS:
        assert flag not in argv


def test_setup_rejects_secret_bearing_flags(tmp_path: Path) -> None:
    from pr_reviewer.cli.main import run_setup

    secrets = FileSecretStore(tmp_path / "secrets")
    with pytest.raises(SystemExit):
        run_setup(
            hosted_origin="https://control.example.test",
            secrets=secrets,
            read_secret=lambda _prompt: "sk-x",
            argv=["setup", "--model-key", "sk-x"],
        )
    assert secrets.get("model_key") is None


def test_uninstall_script_preserves_data_by_default() -> None:
    script = REPO / "scripts" / "uninstall.sh"
    text = script.read_text(encoding="utf-8")
    assert "--delete-data" in text
    assert "--confirm-delete" in text
    preserve = [line.strip() for line in text.splitlines() if line.strip() == "reviewer uninstall"]
    assert preserve == ["reviewer uninstall"]


def test_install_script_verifies_checksum_and_rejects_bad_digest(tmp_path: Path) -> None:
    script = REPO / "scripts" / "install.sh"
    payload = tmp_path / "pr-reviewer"
    payload.write_bytes(b"runner-binary")
    digest = hashlib.sha256(b"runner-binary").hexdigest()
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(f"{digest}  pr-reviewer\n", encoding="utf-8")
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    ok = subprocess.run(
        [
            "sh",
            str(script),
            "--archive",
            str(payload),
            "--checksum-file",
            str(sums),
            "--prefix",
            str(prefix),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    assert (prefix / "pr-reviewer").is_file()

    sums.write_text(("0" * 64) + "  pr-reviewer\n", encoding="utf-8")
    bad_prefix = tmp_path / "bad"
    bad_prefix.mkdir()
    bad = subprocess.run(
        [
            "sh",
            str(script),
            "--archive",
            str(payload),
            "--checksum-file",
            str(sums),
            "--prefix",
            str(bad_prefix),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0
    assert not (bad_prefix / "pr-reviewer").is_file()


def test_install_script_has_no_secret_flags() -> None:
    text = (REPO / "scripts" / "install.sh").read_text(encoding="utf-8")
    for flag in HOSTED_FLAGS:
        assert flag not in text


def test_install_runs_in_clean_linux_container(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is required for the clean-container install proof")
    payload = tmp_path / "pr-reviewer"
    payload.write_bytes(b"container-install")
    digest = hashlib.sha256(b"container-install").hexdigest()
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(f"{digest}  pr-reviewer\n", encoding="utf-8")
    script = REPO / "scripts" / "install.sh"
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "65532:65532",
            "-v",
            f"{script}:/install.sh:ro",
            "-v",
            f"{payload}:/pr-reviewer:ro",
            "-v",
            f"{sums}:/SHA256SUMS:ro",
            "busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662",
            "sh",
            "/install.sh",
            "--archive",
            "/pr-reviewer",
            "--checksum-file",
            "/SHA256SUMS",
            "--prefix",
            "/tmp/prefix",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_reviewer_entry_routes_setup() -> None:
    from pr_reviewer.reviewer_entry import _USAGE

    assert "setup" in _USAGE
