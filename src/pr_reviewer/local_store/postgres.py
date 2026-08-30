"""Full-mode local Postgres with pgvector (Runtime Task 7).

This store is what makes repository retrieval possible on the user's machine. It starts only
when select_runtime_mode has granted full mode -- analysis-only is the mode that never indexes
or executes, so standing this up from that decision would be a lie.

The password is generated once, stored in the existing SecretStore (the same primitive as the
runner credential and model keys), and delivered to the container through POSTGRES_PASSWORD_FILE.
It never appears on process argv, never appears in docker-compose.runner.yml, and never appears
on StoreStatus. The on-disk password file is mode 0600 in a mode-0700 directory, matching
FileSecretStore and open_local_store, and is deleted on every successful stop() so it does not
outlive the container that needed it. The secret in the keyring survives so a preserved volume
can be unlocked on the next start.

This module talks to local Postgres with psycopg directly. It must not import the hosted
database client, the hosted control plane, or the operator CLI package.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psycopg

from pr_reviewer.runner.modes import ModeDecision
from pr_reviewer.runner.secrets import SecretStore

LOCAL_PGVECTOR_SECRET_NAME = "local_pgvector_password"
_COMPOSE_VOLUME = "pr_reviewer_pgvector"
_PG_USER = "pr_reviewer"
_PG_DATABASE = "pr_reviewer"
_DEFAULT_COMPOSE = Path(__file__).resolve().parents[3] / "docker-compose.runner.yml"
_MIGRATIONS_DIRECTORY = Path(__file__).with_name("postgres_migrations")
_PASSWORD_DIR_NAME = "pgvector-password"
_PASSWORD_FILE_NAME = "postgres_password"
_PROBE_TABLE = "pr_reviewer_start_probe"


class LocalVectorStoreError(RuntimeError):
    """The local pgvector service cannot start, stop, or satisfy a requested operation."""


class CommandOutput(Protocol):
    @property
    def returncode(self) -> int: ...
    @property
    def stdout(self) -> str: ...
    @property
    def stderr(self) -> str: ...


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], *, timeout: float) -> CommandOutput: ...


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class SubprocessCommandRunner:
    def run(self, args: Sequence[str], *, timeout: float) -> CommandResult:
        import subprocess

        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        except FileNotFoundError:
            return CommandResult(returncode=127, stdout="", stderr="docker: command not found")
        except subprocess.TimeoutExpired as exc:
            return CommandResult(returncode=1, stdout="", stderr=str(exc))
        return CommandResult(
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )


@dataclass(frozen=True)
class StoreStatus:
    running: bool
    healthy: bool
    bound_host: str
    bound_port: int
    volume_name: str
    url: str


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LocalVectorStore:
    def __init__(
        self,
        *,
        secrets: SecretStore,
        mode: ModeDecision,
        work_directory: Path,
        command_runner: CommandRunner | None = None,
        port: int | None = None,
        compose_file: Path | None = None,
    ) -> None:
        self._secrets = secrets
        self._mode = mode
        self._work_directory = Path(work_directory)
        self._command_runner: CommandRunner = (
            command_runner if command_runner is not None else SubprocessCommandRunner()
        )
        self._uses_injected_runner = command_runner is not None
        self._requested_port = port
        self._port = port
        self._compose_file = compose_file if compose_file is not None else _DEFAULT_COMPOSE
        self._project = _project_name(self._work_directory)
        self._started = False

    @property
    def password_file_path(self) -> Path:
        return self._work_directory / _PASSWORD_DIR_NAME / _PASSWORD_FILE_NAME

    def start(self) -> StoreStatus:
        if self._mode.granted_mode != "full":
            raise LocalVectorStoreError(
                "local pgvector starts only in full mode; "
                f"select_runtime_mode granted {self._mode.granted_mode!r}"
            )

        port = self._requested_port if self._requested_port is not None else _pick_free_port()
        if _port_in_use("127.0.0.1", port):
            raise LocalVectorStoreError(f"port 127.0.0.1:{port} is already in use")
        self._port = port

        password = self._secrets.get(LOCAL_PGVECTOR_SECRET_NAME)
        if password is None:
            password = secrets.token_urlsafe(32)
            self._secrets.set(LOCAL_PGVECTOR_SECRET_NAME, password)
        self._write_password_file(password)

        result = self._compose(
            ["up", "-d", "--wait", "--wait-timeout", "90"],
            timeout=120.0,
        )
        if result.returncode != 0:
            self._remove_password_file()
            raise LocalVectorStoreError(
                f"failed to start local pgvector: {result.stderr.strip() or result.stdout.strip()}"
            )
        self._started = True
        if not self._uses_injected_runner:
            self._wait_until_accepts_connections()
        return self._status(running=True, healthy=not self._uses_injected_runner)

    def migrate(self) -> None:
        sql_files = sorted(_MIGRATIONS_DIRECTORY.glob("*.sql"))
        if not sql_files:
            raise LocalVectorStoreError("no local pgvector migrations found")
        with psycopg.connect(self._connection_url()) as conn:
            conn.autocommit = True
            for path in sql_files:
                conn.execute(path.read_text(encoding="utf-8"))

    def health(self) -> StoreStatus:
        running = (
            self._compose_is_running()
            if self._started or not self._uses_injected_runner
            else False
        )
        healthy = running and self._can_connect()
        return self._status(running=running, healthy=healthy)

    def stop(self, preserve_data: bool, *, confirm_delete: bool = False) -> None:
        if not preserve_data and not confirm_delete:
            raise LocalVectorStoreError(
                "refusing to delete the pgvector volume without confirm_delete=True"
            )
        args = ["down"] if preserve_data else ["down", "-v", "--remove-orphans"]
        result = self._compose(args, timeout=60.0)
        self._remove_password_file()
        self._started = False
        if result.returncode != 0 and not self._uses_injected_runner:
            raise LocalVectorStoreError(
                f"failed to stop local pgvector: {result.stderr.strip() or result.stdout.strip()}"
            )

    def extension_present(self, name: str) -> bool:
        with psycopg.connect(self._connection_url()) as conn:
            row = conn.execute(
                "select 1 from pg_extension where extname = %s", (name,)
            ).fetchone()
        return row is not None

    def write_probe_row(self, value: str) -> None:
        with psycopg.connect(self._connection_url()) as conn:
            conn.execute(
                f"create table if not exists {_PROBE_TABLE} "
                "(id integer primary key, value text not null)"
            )
            conn.execute(f"delete from {_PROBE_TABLE}")
            conn.execute(
                f"insert into {_PROBE_TABLE} (id, value) values (1, %s)", (value,)
            )
            conn.commit()

    def read_probe_row(self) -> str | None:
        with psycopg.connect(self._connection_url()) as conn:
            row = conn.execute(
                f"select value from {_PROBE_TABLE} where id = 1"
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def volume_exists(self, volume_name: str) -> bool:
        result = self._run(
            ["docker", "volume", "inspect", volume_name],
            timeout=15.0,
        )
        return result.returncode == 0

    def _write_password_file(self, password: str) -> None:
        path = self.password_file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        path.write_text(password, encoding="utf-8")
        os.chmod(path, 0o600)

    def _remove_password_file(self) -> None:
        self.password_file_path.unlink(missing_ok=True)

    def _compose(self, args: list[str], *, timeout: float) -> CommandOutput:
        argv = [
            "docker",
            "compose",
            "-f",
            str(self._compose_file),
            "-p",
            self._project,
            *args,
        ]
        return self._run(argv, timeout=timeout)

    def _run(self, args: list[str], *, timeout: float) -> CommandOutput:
        env_port = str(self._port) if self._port is not None else "54331"
        extra = {
            "PR_REVIEWER_PG_PASSWORD_FILE": str(self.password_file_path),
            "PR_REVIEWER_PG_PORT": env_port,
            "PR_REVIEWER_PG_UID": str(os.getuid()),
            "PR_REVIEWER_PG_GID": str(os.getgid()),
        }
        if isinstance(self._command_runner, SubprocessCommandRunner):
            return self._run_with_env(args, timeout=timeout, extra_env=extra)
        return self._command_runner.run(args, timeout=timeout)

    def _run_with_env(
        self, args: list[str], *, timeout: float, extra_env: dict[str, str]
    ) -> CommandResult:
        import subprocess

        env = os.environ.copy()
        env.update(extra_env)
        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                env=env,
            )
        except FileNotFoundError:
            return CommandResult(returncode=127, stdout="", stderr="docker: command not found")
        except subprocess.TimeoutExpired as exc:
            return CommandResult(returncode=1, stdout="", stderr=str(exc))
        return CommandResult(
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )

    def _compose_is_running(self) -> bool:
        result = self._compose(["ps", "-q", "--status", "running"], timeout=15.0)
        return result.returncode == 0 and bool(result.stdout.strip())

    def _can_connect(self) -> bool:
        if self._port is None:
            return False
        try:
            with psycopg.connect(self._connection_url(), connect_timeout=1):
                return True
        except Exception:
            return False

    def _wait_until_accepts_connections(self, *, deadline_seconds: float = 90.0) -> None:
        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            if self._can_connect():
                return
            time.sleep(0.5)
        raise LocalVectorStoreError("local pgvector did not accept connections in time")

    def _connection_url(self) -> str:
        password = self._secrets.get(LOCAL_PGVECTOR_SECRET_NAME)
        if password is None or self._port is None:
            raise LocalVectorStoreError("local pgvector has not been started")
        return f"postgresql://{_PG_USER}:{password}@127.0.0.1:{self._port}/{_PG_DATABASE}"

    def _redacted_url(self) -> str:
        port = self._port if self._port is not None else 0
        return f"postgresql://{_PG_USER}@127.0.0.1:{port}/{_PG_DATABASE}"

    def _volume_name(self) -> str:
        return f"{self._project}_{_COMPOSE_VOLUME}"

    def _status(self, *, running: bool, healthy: bool) -> StoreStatus:
        return StoreStatus(
            running=running,
            healthy=healthy,
            bound_host="127.0.0.1",
            bound_port=self._port if self._port is not None else 0,
            volume_name=self._volume_name(),
            url=self._redacted_url(),
        )


def _project_name(work_directory: Path) -> str:
    digest = hashlib.sha256(str(work_directory.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"prrevpgv{digest}"
