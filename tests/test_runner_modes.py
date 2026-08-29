"""Tests for Runtime Task 6's mode decision: select_runtime_mode.

This is the pure half of "full versus analysis-only is a tested distinction, not a claim".
DockerRuntime.probe() (tests/test_doctor_docker.py) produces a ContainerProbe; this file only
reads one that the test already built. select_runtime_mode must never touch Docker, never run a
command, and never grant full mode when any isolation check failed -- a downgrade to
analysis-only is the only safe grant, because analysis-only is the mode that never executes
untrusted PR code. A fallback that ran the same work on the host is the single worst failure
this project can have (ADR-004 has no reversal trigger).
"""

from __future__ import annotations

from pathlib import Path

from pr_reviewer.containers.runtime import ContainerProbe

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"


def _probe(*, ready: bool = True, failures: tuple[str, ...] = ()) -> ContainerProbe:
    return ContainerProbe(
        docker_cli_found=ready,
        daemon_running=ready,
        socket_accessible=ready,
        image_pull_succeeded=ready,
        runs_as_non_root=ready,
        network_isolated=ready,
        resource_limits_enforced=ready,
        platform_supported=ready,
        failures=failures,
    )


def test_full_mode_is_granted_only_when_every_isolation_check_passed() -> None:
    from pr_reviewer.runner.modes import select_runtime_mode

    decision = select_runtime_mode(_probe(ready=True), "full")

    assert decision.requested_mode == "full"
    assert decision.granted_mode == "full"
    assert decision.retrieval_available is True
    assert decision.verification_available is True
    assert decision.forces_human_approval is False
    assert decision.downgraded is False
    assert decision.disabled_features == ()
    assert decision.probe_failures == ()


def test_analysis_only_sets_retrieval_and_verification_false_and_forces_human_approval() -> None:
    from pr_reviewer.runner.modes import select_runtime_mode

    decision = select_runtime_mode(_probe(ready=True), "analysis_only")

    assert decision.granted_mode == "analysis_only"
    assert decision.retrieval_available is False
    assert decision.verification_available is False
    assert decision.forces_human_approval is True
    assert decision.downgraded is False
    assert decision.disabled_features != ()


def test_full_request_downgrades_to_analysis_only_when_probe_is_not_ready() -> None:
    from pr_reviewer.runner.modes import select_runtime_mode

    failures = ("docker CLI not found on PATH",)
    decision = select_runtime_mode(_probe(ready=False, failures=failures), "full")

    assert decision.requested_mode == "full"
    assert decision.granted_mode == "analysis_only"
    assert decision.downgraded is True
    assert decision.retrieval_available is False
    assert decision.verification_available is False
    assert decision.forces_human_approval is True
    assert decision.probe_failures == failures


def test_downgrade_never_grants_full_mode_with_verification_quietly_disabled() -> None:
    # The dangerous shape: granted_mode="full" while verification_available is False, which would
    # let a caller believe executable verification happened. Analysis-only is the only grant that
    # is allowed to turn verification off.
    from pr_reviewer.runner.modes import select_runtime_mode

    decision = select_runtime_mode(_probe(ready=False, failures=("daemon is not running",)), "full")

    assert not (decision.granted_mode == "full" and decision.verification_available is False)


def test_disabled_features_name_retrieval_verification_and_auto_post() -> None:
    from pr_reviewer.runner.modes import select_runtime_mode

    decision = select_runtime_mode(_probe(ready=False, failures=("x",)), "full")
    listed = " ".join(decision.disabled_features).lower()

    assert "retrieval" in listed
    assert "verification" in listed
    assert "approval" in listed or "auto-post" in listed or "autopost" in listed


def test_analysis_only_lists_the_same_disabled_features_even_when_docker_is_ready() -> None:
    # The user asked for analysis-only on purpose. The disabled list is still required -- doctor
    # shows it before confirm either way, so a voluntary choice and a downgrade cannot disagree
    # about what the mode takes away.
    from pr_reviewer.runner.modes import select_runtime_mode

    requested = select_runtime_mode(_probe(ready=True), "analysis_only")
    downgraded = select_runtime_mode(_probe(ready=False, failures=("x",)), "full")

    assert requested.disabled_features == downgraded.disabled_features
    assert requested.disabled_features != ()


def test_select_runtime_mode_module_never_imports_docker_or_subprocess() -> None:
    source = (SRC_ROOT / "runner" / "modes.py").read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "from subprocess" not in source
    assert "import docker" not in source
    assert "from docker" not in source
