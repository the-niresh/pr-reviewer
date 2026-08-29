"""Full mode versus analysis-only, as a tested decision rather than a claim (Runtime Task 6).

select_runtime_mode is pure: it never touches Docker, never runs a container, and never falls
back to running review work on the host. It only ever reads a ContainerProbe someone else already
produced (containers.docker.DockerRuntime.probe()) and decides what the runner may claim. If
Docker is not ready, the only safe move is to grant analysis-only -- a mode that never executes
anything -- never to grant "full" and let a caller discover later that no container was actually
available. There is no third option here, because ADR-004 has no reversal trigger
(docs/phases/phase-1-system-architecture.md): the runner is not permitted to run untrusted PR
code outside a container under any requested mode.

disabled_features exists for the same reason TraceSegment.placement exists in
observability/trace.py: a reader must be able to see what a decision took away, not have to infer
it from a mode string.
It is populated whenever granted_mode is analysis_only, whether the caller asked for analysis_only
directly or asked for full and was downgraded -- the doctor command shows it before the user
confirms, either way.
"""

from __future__ import annotations

from dataclasses import dataclass

from pr_reviewer.containers.runtime import ContainerProbe
from pr_reviewer.contracts.runner import RunnerMode

# RunnerMode already names the two modes docs/superpowers/plans/2026-08-27-hosted-control-plane-
# local-runner.md defines (full, analysis_only). This alias exists only so this module's public
# interface reads as the plan names it -- RuntimeMode -- without a second, competing Literal.
RuntimeMode = RunnerMode

_DISABLED_IN_ANALYSIS_ONLY: tuple[str, ...] = (
    "repository retrieval (full-mode pgvector indexing of the default branch)",
    "executable verification (reproducing tests and checks in the Docker sandbox)",
    "auto-post without human approval (every finding is queued for manual review)",
)


@dataclass(frozen=True)
class ModeDecision:
    requested_mode: RuntimeMode
    granted_mode: RuntimeMode
    retrieval_available: bool
    verification_available: bool
    forces_human_approval: bool
    downgraded: bool
    disabled_features: tuple[str, ...]
    probe_failures: tuple[str, ...]


def select_runtime_mode(probe: ContainerProbe, requested: RuntimeMode) -> ModeDecision:
    if requested == "analysis_only":
        return ModeDecision(
            requested_mode="analysis_only",
            granted_mode="analysis_only",
            retrieval_available=False,
            verification_available=False,
            forces_human_approval=True,
            downgraded=False,
            disabled_features=_DISABLED_IN_ANALYSIS_ONLY,
            probe_failures=(),
        )

    if probe.full_mode_ready:
        return ModeDecision(
            requested_mode="full",
            granted_mode="full",
            retrieval_available=True,
            verification_available=True,
            forces_human_approval=False,
            downgraded=False,
            disabled_features=(),
            probe_failures=(),
        )

    # Full was requested but Docker isolation is not fully proven. Analysis-only is the only mode
    # that never executes anything, so it is the only safe grant -- this is a downgrade to a mode
    # that runs nothing, never a fallback that runs the same work outside a container.
    return ModeDecision(
        requested_mode="full",
        granted_mode="analysis_only",
        retrieval_available=False,
        verification_available=False,
        forces_human_approval=True,
        downgraded=True,
        disabled_features=_DISABLED_IN_ANALYSIS_ONLY,
        probe_failures=probe.failures,
    )
