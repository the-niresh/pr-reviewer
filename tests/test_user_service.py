"""Tests for the local user service and reviewer start|stop|status|open (Runtime Task 8).

These commands live in runner/cli/service.py, not top-level cli/. They manage the daemon on the
user's machine: systemd --user on Linux, a LaunchAgent on macOS. Neither path needs
administrator rights. A destination under /etc or /Library/LaunchDaemons must be refused with a
clear elevation error rather than silently calling sudo.

Imports of runner.cli.service stay inside test bodies so a missing module fails the test instead
of interrupting collection.
"""

from __future__ import annotations

import socket
from pathlib import Path

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


def test_service_module_never_imports_the_hosted_database_or_control_plane() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    assert "pr_reviewer.db" not in source
    assert "pr_reviewer.control_plane" not in source
    assert "pr_reviewer.cli" not in source
