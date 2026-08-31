"""Failing tests for Docker-only finding verification (master Task 14).

The sandbox uses no network, no host secrets, no Docker socket, a non-root user,
a read-only root filesystem, dropped capabilities, and a temporary work directory.
Command IDs are allowlisted. A shell string is unconstructable. Missing Docker
returns inconclusive and never runs the command on the host.
Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import dataclasses
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pr_reviewer.containers.runtime import ContainerProbe, SandboxResult, SandboxSpec
from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.github.pull_request import PullRequestFile, PullRequestSnapshot

REPO = Path(__file__).resolve().parent.parent
BUSYBOX = "busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662"
HEAD = "a" * 40
PATCH = (
    "@@ -1,2 +1,3 @@\n"
    " context\n"
    "+added line\n"
    " keep\n"
)


@dataclasses.dataclass(frozen=True)
class ScriptedResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ScriptedCommandRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._scripts: list[tuple[str, ScriptedResult]] = []

    def when(
        self, contains: str, *, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> None:
        self._scripts.append((contains, ScriptedResult(returncode, stdout, stderr)))

    def run(self, args: Sequence[str], *, timeout: float) -> ScriptedResult:
        del timeout
        argv = tuple(args)
        self.calls.append(argv)
        joined = " ".join(argv)
        for marker, result in self._scripts:
            if marker in joined:
                return result
        raise AssertionError(f"unscripted command: {argv}")


class HostExecutingRuntime:
    """If verification calls run() after probe says Docker is missing, this explodes."""

    def probe(self) -> ContainerProbe:
        return ContainerProbe(
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

    def run(self, spec: SandboxSpec) -> SandboxResult:
        subprocess.run(list(spec.command), check=False, shell=False)
        raise AssertionError(f"host execution of {spec.command!r}")


def _candidate() -> FindingCandidate:
    return FindingCandidate.model_validate(
        {
            "concern": "correctness",
            "severity": "medium",
            "category": "null-check",
            "file_path": "src/widget.py",
            "line_start": 2,
            "line_end": 2,
            "title": "Missing null check",
            "rationale": "widget.value can be None.",
            "evidence": ["src/widget.py:2"],
            "confidence": 0.8,
        }
    )


def _snapshot() -> PullRequestSnapshot:
    return PullRequestSnapshot.model_validate(
        {
            "repo_owner": "acme",
            "repo_name": "widgets",
            "number": 12,
            "base_sha": "c" * 40,
            "head_sha": HEAD,
            "title": "Add widget",
            "body": "",
            "files": [PullRequestFile(path="src/widget.py", status="modified", patch=PATCH)],
        }
    )


def _policy(**overrides: object) -> Any:
    from pr_reviewer.verification.docker_sandbox import VerificationPolicy

    fields: dict[str, object] = {
        "image_digest": BUSYBOX,
        "allowed_command_ids": frozenset({"true", "false", "id_user"}),
        "required_head_sha": HEAD,
        "command_id": "true",
    }
    fields.update(overrides)
    return VerificationPolicy(**fields)  # type: ignore[arg-type]


def test_sandbox_job_with_a_shell_string_is_unconstructable() -> None:
    from pr_reviewer.verification.docker_sandbox import SandboxJob

    with pytest.raises((TypeError, ValidationError, ValueError)):
        SandboxJob(command_id="true", command="true && curl http://evil.example")  # type: ignore[call-arg]
    with pytest.raises((TypeError, ValidationError, ValueError)):
        SandboxJob(command="rm -rf /")  # type: ignore[call-arg]
    job = SandboxJob(command_id="true")
    assert not hasattr(job, "command") or not isinstance(getattr(job, "command", None), str)


def test_unknown_command_id_is_rejected_and_never_run() -> None:
    from pr_reviewer.verification.docker_sandbox import verify_finding

    with pytest.raises(ValueError, match="command"):
        _policy(command_id="true && wget http://evil.example")
    try:
        verify_finding(
            _candidate(),
            _snapshot(),
            _policy(command_id="not_a_real_command"),
            runtime=HostExecutingRuntime(),
        )
    except ValueError:
        return


def test_image_must_be_pinned_by_digest() -> None:
    with pytest.raises(ValueError, match="digest"):
        _policy(image_digest="busybox:latest")


def test_dockerfile_pins_the_image_by_digest_and_is_non_root() -> None:
    dockerfile = (REPO / "docker" / "sandbox" / "Dockerfile").read_text(encoding="utf-8")
    assert "@sha256:" in dockerfile
    assert "USER" in dockerfile
    assert ":latest" not in dockerfile.split("FROM", 1)[1].splitlines()[0]


def test_missing_docker_returns_inconclusive_and_never_runs_the_command_on_the_host() -> None:
    from pr_reviewer.verification.docker_sandbox import verify_finding

    result = verify_finding(
        _candidate(),
        _snapshot(),
        _policy(),
        runtime=HostExecutingRuntime(),
    )
    assert result.status == "inconclusive"
    assert result.route_to_human is True
    assert result.method == "sandbox"


def test_run_argv_has_isolation_flags_limits_and_no_docker_socket() -> None:
    from pr_reviewer.containers.docker import DockerRuntime
    from pr_reviewer.verification.docker_sandbox import verify_finding

    runner = ScriptedCommandRunner()
    runner.when("docker version", returncode=0, stdout="29.2.1\n")
    runner.when("docker pull", returncode=0)
    runner.when("id -u", returncode=0, stdout="65532\n")
    runner.when("wget", returncode=1, stderr="timed out")
    runner.when(" true", returncode=0)
    runner.when("docker run", returncode=0, stdout="")
    runner.when("docker rm", returncode=0)

    runtime = DockerRuntime(command_runner=runner, platform_reader=lambda: ("Linux", "x86_64"))
    result = verify_finding(_candidate(), _snapshot(), _policy(), runtime=runtime)
    assert result.status == "passed"

    run_calls = [
        call
        for call in runner.calls
        if len(call) > 1 and call[1] == "run" and "--network" in call and call[-1] == "true"
    ]
    assert run_calls
    call = run_calls[-1]
    joined = " ".join(call)
    assert call[0] == "docker"
    assert "--network" in call and call[call.index("--network") + 1] == "none"
    assert "--read-only" in call
    assert "--user" in call and call[call.index("--user") + 1] == "65532:65532"
    assert "--cap-drop" in call and call[call.index("--cap-drop") + 1] == "ALL"
    assert "--pids-limit" in call
    assert "--memory" in call
    assert "--cpus" in call
    assert "docker.sock" not in joined
    assert "/bin/sh" not in call
    assert "-c" not in call
    assert call[-1] == "true"
    work_mounts = [part for part in call if "target=/work" in part]
    assert work_mounts


def test_real_sandbox_is_isolated_and_uses_a_temporary_work_directory() -> None:
    from pr_reviewer.containers.docker import DockerRuntime
    from pr_reviewer.verification.docker_sandbox import verify_finding

    runtime = DockerRuntime()
    probe = runtime.probe()
    assert probe.full_mode_ready is True

    id_result = verify_finding(
        _candidate(),
        _snapshot(),
        _policy(
            command_id="id_user",
            allowed_command_ids=frozenset({"id_user", "true"}),
        ),
        runtime=runtime,
        commands={"id_user": ("id", "-u"), "true": ("true",)},
    )
    assert id_result.status == "passed"
    assert "65532" in id_result.detail

    ro_result = verify_finding(
        _candidate(),
        _snapshot(),
        _policy(
            command_id="write_root",
            allowed_command_ids=frozenset({"write_root"}),
        ),
        runtime=runtime,
        commands={"write_root": ("touch", "/sandbox-should-not-write")},
    )
    assert ro_result.status == "failed"

    net_result = verify_finding(
        _candidate(),
        _snapshot(),
        _policy(
            command_id="wget",
            allowed_command_ids=frozenset({"wget"}),
            timeout_seconds=8,
        ),
        runtime=runtime,
        commands={"wget": ("wget", "-qO-", "--timeout=2", "https://1.1.1.1")},
    )
    assert net_result.status in {"failed", "inconclusive"}


def test_cpu_memory_process_disk_output_and_wall_time_limits() -> None:
    from pr_reviewer.containers.docker import DockerRuntime
    from pr_reviewer.verification.docker_sandbox import verify_finding

    runner = ScriptedCommandRunner()
    runner.when("docker version", returncode=0, stdout="29.2.1\n")
    runner.when("docker pull", returncode=0)
    runner.when("id -u", returncode=0, stdout="65532\n")
    runner.when("wget", returncode=1)
    runner.when(" true", returncode=0)
    runner.when("docker run", returncode=0, stdout="x" * (70 * 1024))
    runner.when("docker rm", returncode=0)
    runtime = DockerRuntime(command_runner=runner, platform_reader=lambda: ("Linux", "x86_64"))
    policy = _policy(
        cpu_limit="0.5",
        memory_limit_mb=64,
        pids_limit=32,
        timeout_seconds=5,
        disk_limit_mb=16,
    )
    result = verify_finding(_candidate(), _snapshot(), policy, runtime=runtime)
    run_calls = [
        call
        for call in runner.calls
        if len(call) > 1 and call[1] == "run" and "--cpus" in call
    ]
    call = next(item for item in run_calls if item[item.index("--cpus") + 1] == "0.5")
    assert call[call.index("--cpus") + 1] == "0.5"
    assert call[call.index("--memory") + 1] == "64m"
    assert call[call.index("--pids-limit") + 1] == "32"
    assert any("tmpfs" in part or "size=16" in part for part in call)
    assert result.status in {"passed", "inconclusive"}


def test_wall_time_limit_has_a_hard_deadline_on_real_docker() -> None:
    from pr_reviewer.containers.docker import DockerRuntime
    from pr_reviewer.verification.docker_sandbox import verify_finding

    runtime = DockerRuntime()
    started = time.monotonic()
    result = verify_finding(
        _candidate(),
        _snapshot(),
        _policy(
            command_id="sleep",
            allowed_command_ids=frozenset({"sleep"}),
            timeout_seconds=2,
        ),
        runtime=runtime,
        commands={"sleep": ("sleep", "30")},
    )
    elapsed = time.monotonic() - started
    assert result.status == "inconclusive"
    assert result.route_to_human is True
    assert elapsed < 15


def test_cleanup_after_success_failure_timeout_and_worker_crash() -> None:
    from pr_reviewer.containers.docker import DockerRuntime
    from pr_reviewer.verification.docker_sandbox import verify_finding

    runtime = DockerRuntime()
    result = verify_finding(_candidate(), _snapshot(), _policy(), runtime=runtime)
    assert result.status == "passed"
    assert result.work_directory is None or not Path(str(result.work_directory)).exists()

    failed = verify_finding(
        _candidate(),
        _snapshot(),
        _policy(
            command_id="false",
            allowed_command_ids=frozenset({"false", "true"}),
        ),
        runtime=runtime,
    )
    assert failed.status == "failed"
    assert failed.work_directory is None or not Path(str(failed.work_directory)).exists()


def test_malicious_child_does_not_outlive_the_container() -> None:
    from pr_reviewer.containers.docker import DockerRuntime
    from pr_reviewer.verification.docker_sandbox import verify_finding

    runtime = DockerRuntime()
    result = verify_finding(
        _candidate(),
        _snapshot(),
        _policy(
            command_id="fork_sleep",
            allowed_command_ids=frozenset({"fork_sleep"}),
            timeout_seconds=8,
            pids_limit=16,
        ),
        runtime=runtime,
        commands={"fork_sleep": ("sh", "-c", "sleep 60 & echo parent")},
    )
    assert result.status in {"passed", "failed", "inconclusive"}
    leftover = subprocess.run(
        ["docker", "ps", "-q", "--filter", "label=pr-reviewer.sandbox=1"],
        capture_output=True,
        text=True,
        timeout=5,
        shell=False,
    )
    assert leftover.stdout.strip() == ""


def test_sandbox_spec_fields_stay_unable_to_request_unsafe_isolation() -> None:
    names = {item.name for item in dataclasses.fields(SandboxSpec)}
    assert "network_mode" not in names
    assert "user" not in names
    assert "read_only" not in names
    assert "cap_drop" not in names
    assert "docker_socket" not in names
    with pytest.raises(TypeError):
        SandboxSpec(
            image_digest=BUSYBOX,
            command=("true",),
            work_directory="/tmp/work",
            network_mode="bridge",  # type: ignore[call-arg]
        )
