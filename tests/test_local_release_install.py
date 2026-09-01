"""Install a locally built versioned release asset in a clean Linux container."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUSYBOX = "busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662"
ASSET_NAME = "pr-reviewer-0.1.0-compose.release.yml"


def test_local_versioned_asset_installs_in_clean_linux_container(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is required for the local versioned-asset install proof")
    dest = tmp_path / "dist"
    built = subprocess.run(
        ["sh", str(REPO / "scripts" / "build-local-release.sh"), str(dest)],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
    )
    assert built.returncode == 0, built.stderr + built.stdout
    asset = dest / ASSET_NAME
    sums = dest / "SHA256SUMS"
    assert asset.is_file()
    assert ASSET_NAME in sums.read_text(encoding="utf-8")
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "65532:65532",
            "-v",
            f"{REPO / 'scripts' / 'install.sh'}:/install.sh:ro",
            "-v",
            f"{asset}:/{ASSET_NAME}:ro",
            "-v",
            f"{sums}:/SHA256SUMS:ro",
            BUSYBOX,
            "sh",
            "/install.sh",
            "--archive",
            f"/{ASSET_NAME}",
            "--checksum-file",
            "/SHA256SUMS",
            "--prefix",
            "/tmp/prefix",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"{ASSET_NAME}: OK" in result.stdout
