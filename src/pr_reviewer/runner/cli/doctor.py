"""`reviewer doctor` (Runtime Task 6): the onboarding check that decides full mode versus
analysis-only as a proven fact, not a claim the user has to trust.

This command never runs untrusted code. It calls ContainerRuntime.probe() -- diagnostic commands
this module owns, against a throwaway probe image -- and never ContainerRuntime.run(), which is
reserved for real PR verification elsewhere. If Docker is not ready, this command does not retry
on the host, does not offer to install Docker, and does not silently proceed in full mode; it
downgrades to analysis-only through select_runtime_mode and shows the user exactly what that
downgrade disables before asking them to confirm.

This module is runner-side (see runner/cli/__init__.py): no pr_reviewer.db, no
pr_reviewer.control_plane, no pr_reviewer.cli. It must be safe to run on a machine that has never
had, and will never have, hosted database credentials.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import cast

from pr_reviewer.containers.docker import DockerRuntime
from pr_reviewer.containers.runtime import ContainerProbe, ContainerRuntime
from pr_reviewer.runner.modes import ModeDecision, RuntimeMode, select_runtime_mode

_PROBE_LABELS: tuple[tuple[str, str], ...] = (
    ("platform_supported", "supported platform"),
    ("docker_cli_found", "docker CLI found"),
    ("daemon_running", "daemon running"),
    ("socket_accessible", "socket accessible"),
    ("image_pull_succeeded", "image pull succeeds"),
    ("runs_as_non_root", "container runs as non-root"),
    ("network_isolated", "container has no network access"),
    ("resource_limits_enforced", "resource limits enforced"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reviewer doctor",
        description="Check whether Docker isolation actually works, and select a runtime mode.",
    )
    parser.add_argument(
        "--mode",
        dest="requested_mode",
        choices=["full", "analysis_only"],
        default="full",
        help="The mode to try to enable (default: full)",
    )
    parser.add_argument(
        "--yes",
        dest="assume_yes",
        action="store_true",
        help="Confirm analysis-only mode non-interactively",
    )
    return parser


def run(
    args: Sequence[str],
    *,
    runtime: ContainerRuntime | None = None,
    confirm: Callable[[], bool] | None = None,
) -> int:
    parsed = build_parser().parse_args(args)
    active_runtime = runtime if runtime is not None else DockerRuntime()

    probe = active_runtime.probe()
    _print_probe_report(probe)

    decision = select_runtime_mode(probe, cast(RuntimeMode, parsed.requested_mode))
    _print_mode_decision(decision)

    if decision.granted_mode == "full":
        return 0

    confirmed = (
        True
        if parsed.assume_yes
        else confirm()
        if confirm is not None
        else _prompt_confirm()
    )
    if not confirmed:
        print("Not confirmed. Stopping without enabling analysis-only mode.", file=sys.stderr)
        return 1
    return 0


def _print_probe_report(probe: ContainerProbe) -> None:
    print("Docker isolation checks:")
    for field_name, label in _PROBE_LABELS:
        passed = getattr(probe, field_name)
        mark = "OK" if passed else "FAIL"
        print(f"  [{mark}] {label}")
    if probe.failures:
        print("Reasons:")
        for reason in probe.failures:
            print(f"  - {reason}")


def _print_mode_decision(decision: ModeDecision) -> None:
    print()
    if decision.granted_mode == "full":
        print("Full mode is available: every required Docker isolation check passed.")
        return

    if decision.downgraded:
        print(f"Requested {decision.requested_mode} mode, but it is not available yet:")
        for reason in decision.probe_failures:
            print(f"  - {reason}")
        print()

    print("Analysis-only mode disables:")
    for feature in decision.disabled_features:
        print(f"  - {feature}")
    print()


def _prompt_confirm() -> bool:
    answer = input("Continue in analysis-only mode? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def main(argv: Sequence[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
