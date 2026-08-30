"""Tests for the local user service and reviewer start|stop|status|open (Runtime Task 8).

These commands live in runner/cli/service.py, not top-level cli/. They manage the daemon on the
user's machine: systemd --user on Linux, a LaunchAgent on macOS. Neither path needs
administrator rights. A destination under /etc or /Library/LaunchDaemons must be refused with a
clear elevation error rather than silently calling sudo.

Imports of runner.cli.service stay inside test bodies so a missing module fails the test instead
of interrupting collection.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "pr_reviewer"
SERVICE = SRC_ROOT / "runner" / "cli" / "service.py"


def _closed_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_linux_user_unit_is_written_under_the_home_directory_not_etc(tmp_path: Path) -> None:
    from pr_reviewer.runner.cli.service import install_user_service

    install_user_service(platform="linux", home=tmp_path)
    unit = tmp_path / ".config" / "systemd" / "user" / "pr-reviewer.service"
    assert unit.is_file()
    text = unit.read_text(encoding="utf-8")
    assert "WantedBy=default.target" in text
    assert "Restart=" in text
    assert "/etc/systemd" not in text


def test_macos_launch_agent_is_written_under_the_home_directory(tmp_path: Path) -> None:
    from pr_reviewer.runner.cli.service import install_user_service

    install_user_service(platform="darwin", home=tmp_path)
    plist = tmp_path / "Library" / "LaunchAgents" / "com.pr-reviewer.plist"
    assert plist.is_file()
    text = plist.read_text(encoding="utf-8")
    assert "RunAtLoad" in text
    assert "/Library/LaunchDaemons" not in text


def test_install_refuses_a_system_path_that_would_need_elevation(tmp_path: Path) -> None:
    from pr_reviewer.runner.cli.service import LocalServiceError, install_user_service

    with pytest.raises(LocalServiceError, match="(?i)administrator|elevation|sudo"):
        install_user_service(
            platform="linux",
            home=tmp_path,
            destination=Path("/etc/systemd/system/pr-reviewer.service"),
        )


def test_status_is_not_running_when_the_local_port_is_closed() -> None:
    from pr_reviewer.runner.cli.service import local_service_status

    port = _closed_loopback_port()
    status = local_service_status(host="127.0.0.1", port=port)
    assert status.running is False
    assert status.bound_host == "127.0.0.1"


def test_open_prints_the_url_when_the_browser_cannot_open(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pr_reviewer.runner.cli.service import open_local_ui

    url = "http://127.0.0.1:9/onboarding"

    def exploding_open(target: str) -> bool:
        del target
        raise OSError("no graphical browser")

    exit_code = open_local_ui(url=url, browser_open=exploding_open)
    assert exit_code == 0
    assert url in capsys.readouterr().out


def test_reviewer_usage_lists_the_user_service_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pr_reviewer.reviewer import main as reviewer_main

    exit_code = reviewer_main([])
    assert exit_code == 1
    err = capsys.readouterr().err
    for name in ("start", "stop", "status", "open"):
        assert name in err


def test_start_refuses_a_non_loopback_host(capsys: pytest.CaptureFixture[str]) -> None:
    from pr_reviewer.runner.cli.service import main as service_main

    exit_code = service_main(["start", "--host", "0.0.0.0"])
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "not wired" not in err
    assert "0.0.0.0" in err
    assert "127.0.0.1" in err


def test_start_hands_the_loopback_app_to_uvicorn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pr_reviewer.containers.runtime import ContainerProbe
    from pr_reviewer.runner.cli import service
    from pr_reviewer.runner.secrets import FileSecretStore

    recorded: dict[str, object] = {}

    def fake_run(app: object, *, host: str, port: int, **kwargs: object) -> None:
        del kwargs
        recorded["app"] = app
        recorded["host"] = host
        recorded["port"] = port

    monkeypatch.setenv("PR_REVIEWER_HOSTED_ORIGIN", "https://control.example.test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))

    probe = ContainerProbe(
        docker_cli_found=False,
        daemon_running=False,
        socket_accessible=False,
        image_pull_succeeded=False,
        runs_as_non_root=False,
        network_isolated=False,
        resource_limits_enforced=False,
        platform_supported=True,
        failures=("docker CLI not found on PATH",),
    )
    secrets = FileSecretStore(tmp_path / "secrets")
    service.start_local_onboarding(
        host="127.0.0.1",
        port=8741,
        hosted_origin="https://control.example.test",
        probe=probe,
        secrets=secrets,
        run_server=fake_run,
    )
    assert recorded["host"] == "127.0.0.1"
    assert recorded["port"] == 8741
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = recorded["app"]
    assert isinstance(app, FastAPI)
    client = TestClient(app)
    mode = client.get("/onboarding/mode")
    assert mode.status_code == 200
    assert "disabled_features" in mode.json()


def test_start_serves_onboarding_on_loopback_until_stopped(
    tmp_path: Path,
) -> None:
    port = _closed_loopback_port()
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["XDG_DATA_HOME"] = str(tmp_path / "share")
    env["PR_REVIEWER_HOSTED_ORIGIN"] = "https://control.example.test"
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pr_reviewer.reviewer",
            "start",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 90
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                raise AssertionError(f"start exited {proc.returncode}: {stderr or stdout}")
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/onboarding/mode", timeout=0.5)
            except httpx.HTTPError:
                time.sleep(0.1)
                continue
            assert response.status_code == 200
            assert "disabled_features" in response.json()
            break
        else:
            proc.kill()
            raise AssertionError("start did not serve /onboarding/mode before the deadline")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_service_module_never_imports_the_hosted_database_or_control_plane() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    assert "pr_reviewer.db" not in source
    assert "pr_reviewer.control_plane" not in source
    assert "pr_reviewer.cli" not in source
