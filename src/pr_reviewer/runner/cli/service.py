"""Local user service and reviewer start|stop|status|open (Runtime Task 8).

Installs a systemd --user unit on Linux or a LaunchAgent on macOS, both under the user's home
directory. A destination that would need administrator rights is refused with a clear error
instead of silently calling sudo.

reviewer start binds the loopback onboarding app with uvicorn so the user unit can actually
restart it after login. reviewer open prints the loopback URL when no graphical browser exists.
A headless VPS is a normal install target.
"""

from __future__ import annotations

import argparse
import os
import secrets as secrets_lib
import signal
import socket
import sys
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pr_reviewer.containers.runtime import ContainerProbe
from pr_reviewer.runner.modes import RuntimeMode
from pr_reviewer.runner.secrets import SecretStore, get_secret_store

LINUX_UNIT_RELATIVE = Path(".config") / "systemd" / "user" / "pr-reviewer.service"
DARWIN_PLIST_RELATIVE = Path("Library") / "LaunchAgents" / "com.pr-reviewer.plist"
_DEFAULT_PORT = 8741
_SESSION_SECRET_NAME = "local_session_secret"


class LocalServiceError(RuntimeError):
    """The user service cannot be installed or the requested destination needs elevation."""


@dataclass(frozen=True)
class ServiceStatus:
    running: bool
    bound_host: str
    url: str


def install_user_service(
    *,
    platform: str,
    home: Path,
    destination: Path | None = None,
) -> Path:
    target = destination if destination is not None else _default_destination(platform, home)
    _refuse_system_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if platform == "linux":
        target.write_text(_linux_unit(), encoding="utf-8")
    elif platform == "darwin":
        target.write_text(_darwin_plist(), encoding="utf-8")
    else:
        raise LocalServiceError(f"unsupported platform {platform!r}")
    return target


def local_service_status(*, host: str, port: int) -> ServiceStatus:
    running = _port_open(host, port)
    return ServiceStatus(
        running=running,
        bound_host=host,
        url=f"http://{host}:{port}/onboarding",
    )


def open_local_ui(
    *,
    url: str,
    browser_open: Callable[[str], bool] | None = None,
) -> int:
    opener = browser_open if browser_open is not None else webbrowser.open
    opened = False
    try:
        opened = bool(opener(url))
    except OSError:
        opened = False
    if not opened:
        print(url)
    return 0


def start_local_onboarding(
    *,
    host: str,
    port: int,
    hosted_origin: str,
    probe: ContainerProbe | None = None,
    secrets: SecretStore | None = None,
    run_server: Callable[..., None] | None = None,
    requested_mode: RuntimeMode = "full",
) -> None:
    from pr_reviewer.runner.web.local_auth import PendingPairingClient, create_local_onboarding_app

    if host != "127.0.0.1":
        raise LocalServiceError(f"onboarding binds 127.0.0.1 only, not {host!r}")

    active_probe = probe if probe is not None else _probe()
    store = secrets if secrets is not None else get_secret_store(
        file_fallback_directory=_data_dir() / "secrets"
    )
    session_secret = store.get(_SESSION_SECRET_NAME)
    if not session_secret:
        session_secret = secrets_lib.token_urlsafe(32)
        store.set(_SESSION_SECRET_NAME, session_secret)

    app = create_local_onboarding_app(
        host=host,
        session_secret=session_secret,
        secrets=store,
        pairing_client=PendingPairingClient(hosted_origin),
        probe=active_probe,
        requested_mode=requested_mode,
        hosted_origin=hosted_origin,
    )
    pid_path = _data_dir() / "onboarding.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    runner = run_server if run_server is not None else _uvicorn_run
    try:
        runner(app, host=host, port=port)
    finally:
        pid_path.unlink(missing_ok=True)


def stop_local_service() -> int:
    pid_path = _data_dir() / "onboarding.pid"
    if not pid_path.is_file():
        print("not running")
        return 0
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        print("not running")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_path.unlink(missing_ok=True)
        print("not running")
        return 0
    print("stopped")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="reviewer")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--hosted-origin",
        default=os.environ.get("PR_REVIEWER_HOSTED_ORIGIN", ""),
    )
    parser.add_argument("--mode", choices=["full", "analysis_only"], default="full")
    if not args:
        parser.print_usage(sys.stderr)
        return 1
    command, rest = args[0], args[1:]
    parsed = parser.parse_args(rest)
    url = f"http://127.0.0.1:{parsed.port}/onboarding"

    if command == "status":
        status = local_service_status(host=parsed.host, port=parsed.port)
        print("running" if status.running else "not running")
        return 0 if status.running else 1
    if command == "open":
        return open_local_ui(url=url)
    if command == "start":
        from pr_reviewer.runner.web.local_auth import LocalAuthError

        if parsed.host != "127.0.0.1":
            print(f"onboarding binds 127.0.0.1 only, not {parsed.host!r}", file=sys.stderr)
            return 1
        if not parsed.hosted_origin:
            print(
                "PR_REVIEWER_HOSTED_ORIGIN or --hosted-origin is required",
                file=sys.stderr,
            )
            return 1
        try:
            start_local_onboarding(
                host=parsed.host,
                port=parsed.port,
                hosted_origin=parsed.hosted_origin,
                requested_mode=cast(RuntimeMode, parsed.mode),
            )
        except (LocalServiceError, LocalAuthError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    if command == "stop":
        return stop_local_service()
    print(f"reviewer: unknown service command {command!r}", file=sys.stderr)
    return 1


def _probe() -> ContainerProbe:
    from pr_reviewer.containers.docker import DockerRuntime

    return DockerRuntime().probe()


def _uvicorn_run(app: object, *, host: str, port: int) -> None:
    import uvicorn
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):
        raise TypeError("onboarding server requires a FastAPI app")
    uvicorn.run(app, host=host, port=port)


def _data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "pr-reviewer"
    return Path.home() / ".local" / "share" / "pr-reviewer"


def _default_destination(platform: str, home: Path) -> Path:
    if platform == "linux":
        return home / LINUX_UNIT_RELATIVE
    if platform == "darwin":
        return home / DARWIN_PLIST_RELATIVE
    raise LocalServiceError(f"unsupported platform {platform!r}")


def _refuse_system_path(destination: Path) -> None:
    text = str(destination)
    if text.startswith("/etc/") or "/Library/LaunchDaemons/" in text:
        raise LocalServiceError(
            "refusing a system path that needs administrator elevation; "
            "install the user unit under the home directory instead"
        )


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _linux_unit() -> str:
    return (
        "[Unit]\n"
        "Description=PR Reviewer local runner\n"
        "\n"
        "[Service]\n"
        "ExecStart=reviewer start\n"
        "Restart=on-failure\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _darwin_plist() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.pr-reviewer</string>
  <key>ProgramArguments</key>
  <array>
    <string>reviewer</string>
    <string>start</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
"""
