"""Docker: the only v1 ContainerRuntime (Runtime Task 6, ADR-004).

Every docker invocation in this module is an argv list passed to subprocess with shell=False.
There is no code path here that ever builds a command by string concatenation or passes anything
to /bin/sh -c -- that is what "no fallback to host command execution" and "no shell string" mean
enforced, not just documented.

probe() answers one question per row of the sandbox threat model
(docs/phases/phase-2-security-design-gate.md, section 9): can this Docker installation actually
isolate untrusted code, not merely "is docker on PATH". Each check only runs once the ones before
it succeeded -- there is no point pulling an image against a daemon that is not running, and a
probe that tried anyway would either hang or report a second failure that is really just an
echo of the first. DockerRuntime.probe() uses a real throwaway probe image
(DEFAULT_PROBE_IMAGE), not the image SandboxSpec later pins by digest: this image never sees
untrusted content, only the doctor's own fixed diagnostic commands, so it is fine for it to track
a mutable tag. The image SandboxSpec actually runs PR code in must be pinned by digest
(SandboxSpec.__post_init__ enforces this); that is Phase 10's tool registry to choose, not this
task's.

run() never widens what SandboxSpec can request. --network none, --read-only, --cap-drop ALL,
--security-opt no-new-privileges, and the non-root --user are hardcoded into the argv this method
builds; none of them is a SandboxSpec field, so there is no parameter a caller could set to turn
any of them off (see containers/runtime.py's module docstring for why).
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from pr_reviewer.containers.runtime import ContainerProbe, SandboxResult, SandboxSpec

# Not pinned by digest deliberately -- see module docstring. Only used for the doctor's own
# fixed self-checks, never to run PR content.
DEFAULT_PROBE_IMAGE = "busybox:1.36.1"

# Docker's own client uses this on a subprocess.run OSError for "no such file or directory" (the
# docker binary itself is missing); borrowed from the shell "command not found" convention so
# probe() has one CommandResult shape to read regardless of the failure kind.
_NOT_FOUND_RETURNCODE = 127

_SUPPORTED_PLATFORMS = frozenset({"Linux", "Darwin"})

_UNSUPPORTED_LIMIT_MARKERS = (
    "no memory limit support",
    "no swap limit support",
    "does not support",
    "not supported",
)

# A public, high-availability address with nothing this project runs behind it: reachable if the
# probe container has real network access, unreachable (by --network none) if it does not. Using
# our own infrastructure here would make this check depend on our uptime instead of Docker's
# isolation.
_NETWORK_PROBE_URL = "https://1.1.1.1"

_MAX_OUTPUT_BYTES = 64 * 1024

_SANDBOX_ARGV_FLAGS: tuple[str, ...] = (
    "--rm",
    "--network",
    "none",
    "--read-only",
    "--user",
    "65532:65532",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
)


class CommandOutput(Protocol):
    @property
    def returncode(self) -> int: ...
    @property
    def stdout(self) -> str: ...
    @property
    def stderr(self) -> str: ...


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], *, timeout: float) -> CommandOutput: ...


class CommandTimeoutError(Exception):
    """Raised by a CommandRunner when a command exceeds its timeout. run() catches this and
    reports SandboxResult.timed_out=True; it must never propagate into retrying the same work
    outside a container.
    """


class SubprocessCommandRunner:
    """The real CommandRunner. shell=False on every call -- see module docstring."""

    def run(self, args: Sequence[str], *, timeout: float) -> CommandResult:
        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        except FileNotFoundError:
            return CommandResult(
                returncode=_NOT_FOUND_RETURNCODE, stdout="", stderr="docker: command not found"
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandTimeoutError(str(exc)) from exc
        return CommandResult(
            returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
        )


def _real_platform() -> tuple[str, str]:
    return platform.system(), platform.machine()


def _classify_connectivity(result: CommandOutput) -> tuple[bool, bool, bool]:
    """Returns (docker_cli_found, daemon_running, socket_accessible), read from one `docker
    version` call so the three checks agree with each other by construction instead of by three
    separate subprocess calls that could disagree under a race.
    """
    if result.returncode == _NOT_FOUND_RETURNCODE:
        return False, False, False
    if result.returncode == 0:
        return True, True, True
    if "permission denied" in result.stderr.lower():
        # The client could not even open the socket, which is Docker's own message for a user
        # not in the docker group -- it says nothing about whether a daemon is listening.
        return True, True, False
    return True, False, True


def _limits_unsupported(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in _UNSUPPORTED_LIMIT_MARKERS)


def _cap_output(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= _MAX_OUTPUT_BYTES:
        return text, False
    return encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore"), True


class DockerRuntime:
    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        probe_image: str = DEFAULT_PROBE_IMAGE,
        platform_reader: Callable[[], tuple[str, str]] = _real_platform,
        probe_timeout_seconds: float = 30.0,
    ) -> None:
        self._command_runner: CommandRunner = (
            command_runner if command_runner is not None else SubprocessCommandRunner()
        )
        self._probe_image = probe_image
        self._platform_reader = platform_reader
        self._probe_timeout_seconds = probe_timeout_seconds

    def _run(self, args: list[str]) -> CommandOutput:
        return self._command_runner.run(args, timeout=self._probe_timeout_seconds)

    def probe(self) -> ContainerProbe:
        failures: list[str] = []

        system, _machine = self._platform_reader()
        platform_supported = system in _SUPPORTED_PLATFORMS
        if not platform_supported:
            failures.append(
                f"unsupported platform {system!r}: Docker sandboxing requires Linux or Darwin"
            )

        version_result = self._run(["docker", "version", "--format", "{{.Server.Version}}"])
        docker_cli_found, daemon_running, socket_accessible = _classify_connectivity(
            version_result
        )
        if not docker_cli_found:
            failures.append("docker CLI not found on PATH")
        elif not socket_accessible:
            failures.append(
                "Docker socket access denied (permission error connecting to the daemon)"
            )
        elif not daemon_running:
            failures.append("Docker daemon is not running")

        image_pull_succeeded = False
        runs_as_non_root = False
        network_isolated = False
        resource_limits_enforced = False

        if docker_cli_found and daemon_running and socket_accessible:
            pull_result = self._run(["docker", "pull", "--quiet", self._probe_image])
            image_pull_succeeded = pull_result.returncode == 0
            if not image_pull_succeeded:
                failures.append(f"failed to pull probe image {self._probe_image!r}")
            else:
                nonroot_result = self._run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--user",
                        "65532:65532",
                        self._probe_image,
                        "id",
                        "-u",
                    ]
                )
                runs_as_non_root = (
                    nonroot_result.returncode == 0
                    and nonroot_result.stdout.strip() not in {"", "0"}
                )
                if not runs_as_non_root:
                    failures.append("probe container ran as root")

                network_result = self._run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        self._probe_image,
                        "wget",
                        "-qO-",
                        "--timeout=2",
                        _NETWORK_PROBE_URL,
                    ]
                )
                network_isolated = network_result.returncode != 0
                if not network_isolated:
                    failures.append("probe container reached the network with --network none")

                limits_result = self._run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--memory",
                        "64m",
                        "--pids-limit",
                        "64",
                        self._probe_image,
                        "true",
                    ]
                )
                resource_limits_enforced = (
                    limits_result.returncode == 0
                    and not _limits_unsupported(limits_result.stderr)
                )
                if not resource_limits_enforced:
                    failures.append("Docker did not enforce memory/pids resource limits")
        else:
            failures.append(
                "skipped image pull, non-root, network, and resource-limit checks: "
                "Docker is not reachable"
            )

        return ContainerProbe(
            docker_cli_found=docker_cli_found,
            daemon_running=daemon_running,
            socket_accessible=socket_accessible,
            image_pull_succeeded=image_pull_succeeded,
            runs_as_non_root=runs_as_non_root,
            network_isolated=network_isolated,
            resource_limits_enforced=resource_limits_enforced,
            platform_supported=platform_supported,
            failures=tuple(failures),
        )

    def run(self, spec: SandboxSpec) -> SandboxResult:
        argv = [
            "docker",
            "run",
            *_SANDBOX_ARGV_FLAGS,
            "--pids-limit",
            str(spec.pids_limit),
            "--memory",
            f"{spec.memory_limit_mb}m",
            "--cpus",
            spec.cpu_limit,
            "--mount",
            f"type=bind,source={spec.work_directory},target=/work",
            spec.image_digest,
            *spec.command,
        ]
        try:
            result = self._command_runner.run(argv, timeout=spec.timeout_seconds)
        except CommandTimeoutError:
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr="sandbox command exceeded its timeout",
                timed_out=True,
                output_truncated=False,
            )
        stdout, stdout_truncated = _cap_output(result.stdout)
        stderr, stderr_truncated = _cap_output(result.stderr)
        return SandboxResult(
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            output_truncated=stdout_truncated or stderr_truncated,
        )
