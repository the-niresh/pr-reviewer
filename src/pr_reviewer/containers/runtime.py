"""The container runtime contract (Runtime Task 6).

Docker is the only v1 implementation of ContainerRuntime (containers/docker.py). This module
defines the interface and the two typed shapes that cross it, SandboxSpec and SandboxResult, plus
ContainerProbe, the isolation-check report that decides whether full mode may exist at all.

The hardest decision here is what SandboxSpec is allowed to contain. The task names one
constraint explicitly -- no shell-string field, because a spec that can carry a shell string is a
spec that can carry an injection -- but the sandbox threat model
(docs/phases/phase-2-security-design-gate.md, section 9) names eight controls, not one: no
network, no host mounts beyond one scoped work directory, no Docker socket, non-root, read-only
root filesystem, dropped capabilities, resource and wall-clock limits, and an image pinned by
digest. A SandboxSpec field for any of "no network" or "non-root" would invite exactly the mistake
the no-shell-string rule exists to avoid one level up: a caller could construct a spec with
network enabled or running as root, and every future reviewer of that call site would have to
notice by reading the value, not by the type system. So SandboxSpec carries only what genuinely
varies per invocation -- the pinned image, the command to run as argv (never a string a shell
could parse), the one work directory to mount, and the resource ceiling -- and DockerRuntime.run
(containers/docker.py) applies every other control unconditionally, with no parameter that could
turn one off. Command is a tuple of argv strings, executed as the container's entrypoint
arguments and never concatenated or passed through /bin/sh -c; that is what "no shell-string
field" means in code, not merely "no field literally named command_string".

ContainerProbe exists because ADR-004 is explicit that Docker being installed and running is not
proof that isolation works (docs/phases/phase-1-system-architecture.md, ADR-004; phase-2-security-
design-gate.md section 9). full_mode_ready is true only once every one of the checks below has
been proven by actually running something, not by checking that a binary exists on PATH.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ContainerProbe:
    """One isolation check per row of the sandbox threat model table this project can actually
    verify before trusting Docker with untrusted PR code. Each field is a fact this probe proved
    by running something -- never a guess from "docker is on PATH" or "the daemon answered a
    ping".
    """

    docker_cli_found: bool
    daemon_running: bool
    socket_accessible: bool
    image_pull_succeeded: bool
    runs_as_non_root: bool
    network_isolated: bool
    resource_limits_enforced: bool
    platform_supported: bool
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def full_mode_ready(self) -> bool:
        return (
            self.docker_cli_found
            and self.daemon_running
            and self.socket_accessible
            and self.image_pull_succeeded
            and self.runs_as_non_root
            and self.network_isolated
            and self.resource_limits_enforced
            and self.platform_supported
        )


@dataclass(frozen=True)
class SandboxSpec:
    """No field here can hold a command a shell would interpret. `command` is argv: it is passed
    to the container's entrypoint as a list of arguments, the same way ContainerRuntime.run must
    invoke Docker itself -- never through a shell, never by string concatenation. There is
    deliberately no field for network mode, user, filesystem mode, dropped capabilities, or the
    Docker socket: those are never caller-configurable (see module docstring), so there is no way
    to construct a spec that asks for any of them to be relaxed.
    """

    image_digest: str
    command: tuple[str, ...]
    work_directory: str
    cpu_limit: str = "1"
    memory_limit_mb: int = 512
    pids_limit: int = 128
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if isinstance(self.command, str):
            raise TypeError("SandboxSpec.command must be an argv tuple, not a shell string")
        if not isinstance(self.command, tuple) or not self.command:
            raise ValueError("SandboxSpec.command must be a non-empty argv tuple")
        if not all(isinstance(part, str) for part in self.command):
            raise TypeError("SandboxSpec.command parts must each be a string")
        if "@sha256:" not in self.image_digest:
            raise ValueError(
                f"SandboxSpec.image_digest must be pinned by digest, got {self.image_digest!r}"
            )


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool


class ContainerRuntime(Protocol):
    def probe(self) -> ContainerProbe: ...
    def run(self, spec: SandboxSpec) -> SandboxResult: ...
