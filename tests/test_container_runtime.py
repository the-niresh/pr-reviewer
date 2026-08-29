"""Tests for the container runtime contract itself (Runtime Task 6): SandboxSpec, SandboxResult,
and ContainerProbe.full_mode_ready. containers/docker.py's DockerRuntime is exercised separately
in tests/test_doctor_docker.py; this file is about the shapes, not any particular implementation.

The point under test in the SandboxSpec cases is not "the field is validated" -- it is "there is no
field a shell string could occupy at all". command is argv, a tuple of separate strings, not one
string a shell would parse; that is asserted here by using it as a real argv-shaped tuple, never by
asserting some validator rejects a semicolon.
"""

from __future__ import annotations

import dataclasses

import pytest

from pr_reviewer.containers.runtime import ContainerProbe, SandboxResult, SandboxSpec

DIGEST_IMAGE = "busybox@sha256:" + "a" * 64


def _sandbox_spec(**overrides: object) -> SandboxSpec:
    defaults: dict[str, object] = {
        "image_digest": DIGEST_IMAGE,
        "command": ("pytest", "-q"),
        "work_directory": "/tmp/work",
    }
    defaults.update(overrides)
    return SandboxSpec(**defaults)  # type: ignore[arg-type]


def test_sandbox_spec_has_no_field_that_can_hold_a_shell_string() -> None:
    # The whole point: enumerate every field this dataclass has, and confirm none of them is a
    # single free-form string meant to be interpreted by a shell. command is a tuple (argv), and
    # every other field is either the pinned image, the one work directory, or a numeric/limit
    # value -- nothing resembling "the command to run" as one string.
    field_names = {f.name for f in dataclasses.fields(SandboxSpec)}
    assert field_names == {
        "image_digest",
        "command",
        "work_directory",
        "cpu_limit",
        "memory_limit_mb",
        "pids_limit",
        "timeout_seconds",
    }
    spec = _sandbox_spec()
    assert isinstance(spec.command, tuple)
    assert all(isinstance(part, str) for part in spec.command)


def test_sandbox_spec_rejects_an_empty_command() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _sandbox_spec(command=())


def test_sandbox_spec_rejects_a_shell_string_as_command() -> None:
    # A str is iterable, so a dataclass typed tuple[str, ...] will happily store "rm -rf /" and
    # a later join() would turn that into a shell line. The type annotation is not the guard;
    # construction must refuse a string so a shell command is unrepresentable, not just unwise.
    with pytest.raises((TypeError, ValueError)):
        _sandbox_spec(command="pytest && curl http://evil.example")


def test_sandbox_spec_rejects_an_image_reference_not_pinned_by_digest() -> None:
    with pytest.raises(ValueError, match="pinned by digest"):
        _sandbox_spec(image_digest="busybox:latest")


def test_sandbox_spec_is_frozen() -> None:
    spec = _sandbox_spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.command = ("rm", "-rf", "/")  # type: ignore[misc]


def test_sandbox_result_carries_no_hidden_success_signal_beyond_exit_code_and_flags() -> None:
    result = SandboxResult(
        exit_code=1, stdout="out", stderr="err", timed_out=False, output_truncated=False
    )
    assert result.exit_code == 1
    assert result.timed_out is False
    assert result.output_truncated is False


def _probe(**overrides: object) -> ContainerProbe:
    defaults: dict[str, object] = {
        "docker_cli_found": True,
        "daemon_running": True,
        "socket_accessible": True,
        "image_pull_succeeded": True,
        "runs_as_non_root": True,
        "network_isolated": True,
        "resource_limits_enforced": True,
        "platform_supported": True,
    }
    defaults.update(overrides)
    return ContainerProbe(**defaults)  # type: ignore[arg-type]


def test_full_mode_ready_is_true_only_when_every_check_passes() -> None:
    assert _probe().full_mode_ready is True


@pytest.mark.parametrize(
    "field_name",
    [
        "docker_cli_found",
        "daemon_running",
        "socket_accessible",
        "image_pull_succeeded",
        "runs_as_non_root",
        "network_isolated",
        "resource_limits_enforced",
        "platform_supported",
    ],
)
def test_full_mode_ready_is_false_if_any_single_check_fails(field_name: str) -> None:
    probe = _probe(**{field_name: False})
    assert probe.full_mode_ready is False
