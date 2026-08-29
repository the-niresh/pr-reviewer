"""Failing doctor tests for Runtime Task 6.

Covers DockerRuntime.probe() against each isolation failure the plan names, and the
`reviewer doctor` command that turns that probe into a mode the user can see and confirm.

No test here talks to a real Docker daemon. A scripted CommandRunner is the seam: each case
feeds the argv DockerRuntime would send and returns the stdout/stderr a broken install would
produce. If a test finds itself starting a container or looking at the host's `docker` binary,
that test is in the wrong file.

Never auto-install and never fall back to host execution are tests, not comments. The first is
a source scan (apt-get / brew / get.docker.com cannot appear). The second is behavioural: when
the docker binary is missing, SandboxSpec.command must not be executed as a host argv.
"""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from pr_reviewer.containers.runtime import ContainerProbe, SandboxResult, SandboxSpec

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
DIGEST_IMAGE = "busybox@sha256:" + "a" * 64

_INSTALL_MARKERS = (
    "apt-get",
    "brew install",
    "yum install",
    "dnf install",
    "get.docker.com",
    "curl -fsSL",
    "wget https://",
)


@dataclasses.dataclass(frozen=True)
class ScriptedResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ScriptedCommandRunner:
    """Matches the first scripted predicate that returns True for an argv. An unscripted
    command is a test bug, not a silently-successful docker call.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._scripts: list[tuple[object, ScriptedResult]] = []

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
            assert isinstance(marker, str)
            if marker in joined:
                return result
        raise AssertionError(f"unscripted command: {argv}")


def _runtime(
    runner: ScriptedCommandRunner,
    *,
    system: str = "Linux",
    machine: str = "x86_64",
) -> Any:
    from pr_reviewer.containers.docker import DockerRuntime

    return DockerRuntime(
        command_runner=runner,
        platform_reader=lambda: (system, machine),
    )


def _ready_scripts(runner: ScriptedCommandRunner) -> None:
    runner.when("docker version", returncode=0, stdout="24.0.0\n")
    runner.when("docker pull", returncode=0, stdout="")
    runner.when("id -u", returncode=0, stdout="65532\n")
    runner.when("wget", returncode=1, stderr="wget: download timed out")
    runner.when(" true", returncode=0, stdout="")


def test_probe_reports_missing_docker_cli() -> None:
    runner = ScriptedCommandRunner()
    runner.when("docker version", returncode=127, stderr="docker: command not found")

    probe = _runtime(runner).probe()

    assert probe.docker_cli_found is False
    assert probe.full_mode_ready is False
    assert any("cli" in reason.lower() or "path" in reason.lower() for reason in probe.failures)
    assert probe.image_pull_succeeded is False
    assert probe.runs_as_non_root is False
    assert probe.network_isolated is False
    assert probe.resource_limits_enforced is False
    assert not any(call[0] == "docker" and call[1] == "run" for call in runner.calls)


def test_probe_reports_stopped_daemon() -> None:
    runner = ScriptedCommandRunner()
    runner.when(
        "docker version",
        returncode=1,
        stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
        "Is the docker daemon running?",
    )

    probe = _runtime(runner).probe()

    assert probe.docker_cli_found is True
    assert probe.daemon_running is False
    assert probe.full_mode_ready is False
    assert any("daemon" in reason.lower() for reason in probe.failures)
    assert not any(call[1] == "pull" for call in runner.calls)


def test_probe_reports_denied_socket() -> None:
    runner = ScriptedCommandRunner()
    runner.when(
        "docker version",
        returncode=1,
        stderr="permission denied while trying to connect to the Docker daemon socket "
        "at unix:///var/run/docker.sock",
    )

    probe = _runtime(runner).probe()

    assert probe.docker_cli_found is True
    assert probe.socket_accessible is False
    assert probe.full_mode_ready is False
    assert any(
        "permission" in reason.lower() or "socket" in reason.lower() for reason in probe.failures
    )
    assert not any(call[1] == "pull" for call in runner.calls)


def test_probe_reports_failed_pull() -> None:
    runner = ScriptedCommandRunner()
    runner.when("docker version", returncode=0, stdout="24.0.0\n")
    runner.when(
        "docker pull", returncode=1, stderr="Error response from daemon: pull access denied"
    )

    probe = _runtime(runner).probe()

    assert probe.image_pull_succeeded is False
    assert probe.full_mode_ready is False
    assert any("pull" in reason.lower() for reason in probe.failures)
    assert not any(call[1] == "run" for call in runner.calls)


def test_probe_reports_root_container() -> None:
    runner = ScriptedCommandRunner()
    runner.when("docker version", returncode=0, stdout="24.0.0\n")
    runner.when("docker pull", returncode=0)
    runner.when("id -u", returncode=0, stdout="0\n")
    runner.when("wget", returncode=1, stderr="wget: download timed out")
    runner.when(" true", returncode=0)

    probe = _runtime(runner).probe()

    assert probe.runs_as_non_root is False
    assert probe.full_mode_ready is False
    assert any("root" in reason.lower() for reason in probe.failures)


def test_probe_reports_network_access() -> None:
    runner = ScriptedCommandRunner()
    runner.when("docker version", returncode=0, stdout="24.0.0\n")
    runner.when("docker pull", returncode=0)
    runner.when("id -u", returncode=0, stdout="65532\n")
    runner.when("wget", returncode=0, stdout="<html>reachable</html>")
    runner.when(" true", returncode=0)

    probe = _runtime(runner).probe()

    assert probe.network_isolated is False
    assert probe.full_mode_ready is False
    assert any("network" in reason.lower() for reason in probe.failures)


def test_probe_reports_missing_resource_limits() -> None:
    runner = ScriptedCommandRunner()
    runner.when("docker version", returncode=0, stdout="24.0.0\n")
    runner.when("docker pull", returncode=0)
    runner.when("id -u", returncode=0, stdout="65532\n")
    runner.when("wget", returncode=1, stderr="wget: download timed out")
    runner.when(" true", returncode=0, stderr="WARNING: No memory limit support")

    probe = _runtime(runner).probe()

    assert probe.resource_limits_enforced is False
    assert probe.full_mode_ready is False
    assert any("limit" in reason.lower() for reason in probe.failures)


def test_probe_reports_unsupported_platform() -> None:
    runner = ScriptedCommandRunner()
    _ready_scripts(runner)

    probe = _runtime(runner, system="Windows", machine="AMD64").probe()

    assert probe.platform_supported is False
    assert probe.full_mode_ready is False
    assert any("platform" in reason.lower() for reason in probe.failures)


def test_probe_is_ready_only_when_every_check_passes() -> None:
    runner = ScriptedCommandRunner()
    _ready_scripts(runner)

    probe = _runtime(runner).probe()

    assert probe.full_mode_ready is True
    assert probe.failures == ()


def test_run_never_executes_spec_command_on_the_host_when_docker_is_missing() -> None:
    runner = ScriptedCommandRunner()
    runner.when("docker", returncode=127, stderr="docker: command not found")
    spec = SandboxSpec(
        image_digest=DIGEST_IMAGE,
        command=("pytest", "-q"),
        work_directory="/tmp/work",
    )

    result = _runtime(runner).run(spec)

    assert runner.calls, "run() must still go through docker, even when the binary is missing"
    for call in runner.calls:
        assert call[0] == "docker", f"host execution of {call!r} is the ADR-004 failure"
        assert call != spec.command
    assert result.exit_code != 0 or result.timed_out is True


def test_run_passes_command_as_argv_never_as_a_shell_string() -> None:
    runner = ScriptedCommandRunner()
    runner.when("docker run", returncode=0, stdout="ok\n")
    spec = SandboxSpec(
        image_digest=DIGEST_IMAGE,
        command=("pytest", "-q", "tests/test_x.py"),
        work_directory="/tmp/work",
    )

    _runtime(runner).run(spec)

    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call[0] == "docker"
    assert "sh" not in call
    assert "-c" not in call
    assert "pytest -q tests/test_x.py" not in call
    assert call[-3:] == spec.command
    assert "--network" in call and call[call.index("--network") + 1] == "none"


def test_docker_and_doctor_sources_never_auto_install_docker() -> None:
    sources = [
        SRC_ROOT / "containers" / "docker.py",
        SRC_ROOT / "runner" / "cli" / "doctor.py",
        SRC_ROOT / "runner" / "modes.py",
    ]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for marker in _INSTALL_MARKERS:
            assert marker.lower() not in lowered, (
                f"{path} must never auto-install Docker ({marker!r})"
            )


def test_docker_runtime_never_invokes_a_shell() -> None:
    source = (SRC_ROOT / "containers" / "docker.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "shell" and not (
                    isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                ):
                    raise AssertionError("containers/docker.py passed shell=True (or a non-False)")


def _failing_probe() -> ContainerProbe:
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


class _FakeRuntime:
    def __init__(self, probe: ContainerProbe) -> None:
        self._probe = probe

    def probe(self) -> ContainerProbe:
        return self._probe

    def run(self, spec: SandboxSpec) -> SandboxResult:
        raise AssertionError(f"doctor must never call run() with {spec!r}")


def test_doctor_shows_disabled_features_before_asking_to_confirm_analysis_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen_at_confirm: list[str] = []

    def confirm() -> bool:
        seen_at_confirm.append(capsys.readouterr().out)
        return True

    from pr_reviewer.runner.cli.doctor import run as doctor_run

    exit_code = doctor_run(
        ["--mode", "full"],
        runtime=_FakeRuntime(_failing_probe()),
        confirm=confirm,
    )

    assert exit_code == 0
    assert seen_at_confirm, "doctor must ask for confirmation, not skip straight to analysis-only"
    shown = seen_at_confirm[0].lower()
    assert "analysis-only" in shown or "analysis only" in shown
    assert "retrieval" in shown
    assert "verification" in shown
    assert "approval" in shown or "auto-post" in shown or "autopost" in shown


def test_doctor_exits_nonzero_when_analysis_only_is_not_confirmed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pr_reviewer.runner.cli.doctor import run as doctor_run

    exit_code = doctor_run(
        ["--mode", "full"],
        runtime=_FakeRuntime(_failing_probe()),
        confirm=lambda: False,
    )

    assert exit_code == 1
    assert "not confirmed" in capsys.readouterr().err.lower()


def test_doctor_never_offers_to_install_docker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pr_reviewer.runner.cli.doctor import run as doctor_run

    doctor_run(
        ["--mode", "full", "--yes"],
        runtime=_FakeRuntime(_failing_probe()),
        confirm=lambda: True,
    )

    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    for marker in ("install docker", "apt-get", "brew install", "get.docker.com"):
        assert marker not in output


def test_doctor_on_ready_probe_enables_full_mode_without_confirm(
    capsys: pytest.CaptureFixture[str],
) -> None:
    confirm_called = False

    def confirm() -> bool:
        nonlocal confirm_called
        confirm_called = True
        return True

    ready = ContainerProbe(
        docker_cli_found=True,
        daemon_running=True,
        socket_accessible=True,
        image_pull_succeeded=True,
        runs_as_non_root=True,
        network_isolated=True,
        resource_limits_enforced=True,
        platform_supported=True,
    )
    from pr_reviewer.runner.cli.doctor import run as doctor_run

    exit_code = doctor_run(["--mode", "full"], runtime=_FakeRuntime(ready), confirm=confirm)

    assert exit_code == 0
    assert confirm_called is False
    assert "full mode" in capsys.readouterr().out.lower()


def test_unified_reviewer_entry_dispatches_doctor_without_loading_operator_cli() -> None:
    source = (SRC_ROOT / "reviewer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.add(node.module)

    hosted = {
        name
        for name in top_level_imports
        if name == "pr_reviewer.cli"
        or name.startswith("pr_reviewer.cli.")
        or name == "pr_reviewer.db"
        or name.startswith("pr_reviewer.db.")
        or name == "pr_reviewer.control_plane"
        or name.startswith("pr_reviewer.control_plane.")
    }
    assert not hosted, (
        f"reviewer.py loaded operator/hosted imports at module scope: {sorted(hosted)}"
    )


def test_pyproject_registers_the_unified_reviewer_script() -> None:
    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert 'reviewer = "pr_reviewer.reviewer:main"' in text


def test_reviewer_unknown_subcommand_is_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    from pr_reviewer.reviewer import main as reviewer_main

    exit_code = reviewer_main(["not-a-command"])
    assert exit_code == 1
    assert "unknown subcommand" in capsys.readouterr().err.lower()
