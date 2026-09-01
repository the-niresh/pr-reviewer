"""Failing tests for the installed doctor (master Task 25)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from pr_reviewer.containers.runtime import ContainerProbe

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "pr_reviewer"
HOSTED_PROMPTS = (
    "neon url",
    "github app private key",
    "webhook secret",
    "personal access token",
    "public webhook url",
)


def _failing_probe() -> ContainerProbe:
    return ContainerProbe(
        platform_supported=True,
        docker_cli_found=False,
        daemon_running=False,
        socket_accessible=False,
        image_pull_succeeded=False,
        runs_as_non_root=False,
        network_isolated=False,
        resource_limits_enforced=False,
        failures=("docker CLI found: missing",),
    )


def _ok_probe() -> ContainerProbe:
    return ContainerProbe(
        platform_supported=True,
        docker_cli_found=True,
        daemon_running=True,
        socket_accessible=True,
        image_pull_succeeded=True,
        runs_as_non_root=True,
        network_isolated=True,
        resource_limits_enforced=True,
        failures=(),
    )


def test_doctor_reports_control_plane_pairing_keys_ports_disk_and_docker() -> None:
    from pr_reviewer.cli.doctor import run_doctor

    report = run_doctor(
        hosted_origin="https://control.example.test",
        http_get=lambda url: type("R", (), {"ok": url.endswith("/health")})(),
        paired=True,
        model_key_present=True,
        port_in_use=False,
        free_disk_bytes=2 * 1024**3,
        probe=_ok_probe(),
        requested_mode="full",
    )
    assert report.control_plane_reachable is True
    assert report.paired is True
    assert report.model_key_present is True
    assert report.port_available is True
    assert report.disk_ok is True
    assert report.granted_mode == "full"


def test_doctor_shows_analysis_only_limits_before_confirm(capsys: Any) -> None:
    from pr_reviewer.cli.doctor import run_doctor

    confirmed: list[bool] = []

    def confirm() -> bool:
        captured = capsys.readouterr().out
        assert "executable verification" in captured
        confirmed.append(True)
        return True

    report = run_doctor(
        hosted_origin="https://control.example.test",
        http_get=lambda _url: type("R", (), {"ok": False})(),
        paired=False,
        model_key_present=False,
        port_in_use=False,
        free_disk_bytes=2 * 1024**3,
        probe=_failing_probe(),
        requested_mode="full",
        confirm=confirm,
    )
    assert report.granted_mode == "analysis_only"
    assert report.downgraded is True
    assert confirmed == [True]


def test_doctor_and_setup_never_prompt_for_hosted_secrets() -> None:
    paths = (
        SRC / "cli" / "doctor.py",
        SRC / "cli" / "main.py",
        REPO / "scripts" / "install.sh",
        REPO / "scripts" / "uninstall.sh",
        REPO / "docs" / "INSTALL.md",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for prompt in HOSTED_PROMPTS:
            assert prompt not in text, f"{path.name} asks for {prompt}"


def test_installer_cli_does_not_import_hosted_handles() -> None:
    forbidden = ("pr_reviewer.db", "pr_reviewer.control_plane")
    for name in ("doctor.py", "main.py"):
        path = SRC / "cli" / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(item) for item in forbidden)
