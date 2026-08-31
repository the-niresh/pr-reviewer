"""Docker-only verification of allowlisted command IDs.

The model picks an ID from a list a human wrote. It does not compose a command.
SandboxSpec is used as-is: no field is added that could turn isolation off.
If Docker is missing, the result is inconclusive and the command is never run
on the host.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from pr_reviewer.containers.docker import (
    CommandOutput,
    CommandRunner,
    CommandTimeoutError,
    DockerRuntime,
)
from pr_reviewer.containers.runtime import ContainerRuntime, SandboxResult, SandboxSpec
from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.github.pull_request import PullRequestSnapshot

VerificationStatus = Literal["passed", "failed", "inconclusive", "not_applicable"]
VerificationMethod = Literal["sandbox", "static", "not_applicable", "failed"]

DEFAULT_COMMANDS: dict[str, tuple[str, ...]] = {
    "true": ("true",),
    "false": ("false",),
    "id_user": ("id", "-u"),
}

_CLEANUP_SECONDS = 10.0


class SandboxJob(BaseModel):
    """The only thing a caller can name is a command ID. extra=forbid makes a
    shell string field unconstructable, not a runtime rejection.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class VerificationPolicy:
    image_digest: str
    allowed_command_ids: frozenset[str]
    required_head_sha: str
    command_id: str | None = None
    cpu_limit: str = "1"
    memory_limit_mb: int = 512
    pids_limit: int = 128
    timeout_seconds: int = 120
    disk_limit_mb: int = 64

    def __post_init__(self) -> None:
        if "@sha256:" not in self.image_digest:
            raise ValueError("image_digest must be pinned by digest")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a hard deadline greater than 0")
        if self.command_id is not None:
            if self.command_id not in self.allowed_command_ids:
                raise ValueError(f"command id {self.command_id!r} is not allowlisted")
            SandboxJob(command_id=self.command_id)


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    method: VerificationMethod
    route_to_human: bool
    detail: str = ""
    work_directory: str | None = None


def verify_finding(
    candidate: FindingCandidate,
    snapshot: PullRequestSnapshot,
    policy: VerificationPolicy,
    *,
    runtime: ContainerRuntime,
    commands: Mapping[str, tuple[str, ...]] | None = None,
) -> VerificationResult:
    from pr_reviewer.verification.static_checks import check_static

    static = check_static(
        candidate, snapshot, required_head_sha=policy.required_head_sha
    )
    if static.status != "passed":
        return static
    if policy.command_id is None:
        return static

    probe = runtime.probe()
    if not probe.docker_cli_found or not probe.full_mode_ready:
        return VerificationResult(
            status="inconclusive",
            method="sandbox",
            route_to_human=True,
            detail="docker is missing or isolation is not ready; routed to a person",
        )

    registry = {**DEFAULT_COMMANDS, **dict(commands or {})}
    argv = registry.get(policy.command_id)
    if argv is None:
        raise ValueError(f"command id {policy.command_id!r} has no argv")
    SandboxJob(command_id=policy.command_id)

    container_name = f"prrev-sbx-{uuid4().hex[:12]}"
    work = Path(tempfile.mkdtemp(prefix="pr-reviewer-sandbox-"))
    cleanup_deadline = time.monotonic() + _CLEANUP_SECONDS + float(policy.timeout_seconds)
    try:
        guarded = _guard_runtime(
            runtime, container_name=container_name, disk_limit_mb=policy.disk_limit_mb
        )
        spec = SandboxSpec(
            image_digest=policy.image_digest,
            command=argv,
            work_directory=str(work),
            cpu_limit=policy.cpu_limit,
            memory_limit_mb=policy.memory_limit_mb,
            pids_limit=policy.pids_limit,
            timeout_seconds=policy.timeout_seconds,
        )
        raw = guarded.run(spec)
        return _result_from_sandbox(raw)
    finally:
        _cleanup(
            runtime,
            container_name=container_name,
            work=work,
            deadline=cleanup_deadline,
        )


def _result_from_sandbox(raw: SandboxResult) -> VerificationResult:
    detail = (raw.stdout or raw.stderr).strip()
    if raw.timed_out or raw.output_truncated:
        return VerificationResult(
            status="inconclusive",
            method="sandbox",
            route_to_human=True,
            detail=detail or "sandbox timed out or output was truncated",
        )
    if raw.exit_code == 0:
        return VerificationResult(
            status="passed",
            method="sandbox",
            route_to_human=False,
            detail=detail,
        )
    return VerificationResult(
        status="failed",
        method="sandbox",
        route_to_human=True,
        detail=detail,
    )


def _guard_runtime(
    runtime: ContainerRuntime, *, container_name: str, disk_limit_mb: int
) -> ContainerRuntime:
    if not isinstance(runtime, DockerRuntime):
        return runtime
    return DockerRuntime(
        command_runner=_RewriteRunner(
            runtime._command_runner,
            container_name=container_name,
            disk_limit_mb=disk_limit_mb,
        ),
        probe_image=runtime._probe_image,
        platform_reader=runtime._platform_reader,
        probe_timeout_seconds=runtime._probe_timeout_seconds,
    )


class _RewriteRunner:
    """Adds name, label, and a sized tmpfs. Never a Docker socket mount."""

    def __init__(
        self,
        inner: CommandRunner,
        *,
        container_name: str,
        disk_limit_mb: int,
    ) -> None:
        self._inner = inner
        self._container_name = container_name
        self._disk_limit_mb = disk_limit_mb

    def run(self, args: Sequence[str], *, timeout: float) -> CommandOutput:
        argv = list(args)
        if len(argv) >= 2 and argv[0] == "docker" and argv[1] == "run":
            extra = [
                "--name",
                self._container_name,
                "--label",
                "pr-reviewer.sandbox=1",
                "--init",
                "--tmpfs",
                f"/tmp:size={self._disk_limit_mb}m,uid=65532,gid=65532",
            ]
            argv = ["docker", "run", *extra, *argv[2:]]
            joined = " ".join(argv)
            if "docker.sock" in joined:
                raise RuntimeError("refusing to run a sandbox that mounts the Docker socket")
        return self._inner.run(argv, timeout=timeout)


def _cleanup(
    runtime: ContainerRuntime,
    *,
    container_name: str,
    work: Path,
    deadline: float,
) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError(f"TIMEOUT waiting to remove container {container_name}")
    runner = getattr(runtime, "_command_runner", None)
    if runner is not None:
        try:
            runner.run(
                ["docker", "rm", "-f", container_name],
                timeout=remaining,
            )
        except CommandTimeoutError:
            raise RuntimeError(
                f"TIMEOUT waiting to remove container {container_name}"
            ) from None
    shutil.rmtree(work, ignore_errors=True)
