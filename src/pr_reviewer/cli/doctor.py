"""Installed doctor checks. No hosted database or control-plane imports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pr_reviewer.containers.runtime import ContainerProbe
from pr_reviewer.runner.modes import RuntimeMode, select_runtime_mode

MIN_FREE_DISK_BYTES = 1024**3


@dataclass(frozen=True)
class DoctorReport:
    control_plane_reachable: bool
    paired: bool
    model_key_present: bool
    port_available: bool
    disk_ok: bool
    granted_mode: RuntimeMode
    downgraded: bool
    disabled_features: tuple[str, ...]


def run_doctor(
    *,
    hosted_origin: str,
    http_get: Callable[[str], Any],
    paired: bool,
    model_key_present: bool,
    port_in_use: bool,
    free_disk_bytes: int,
    probe: ContainerProbe,
    requested_mode: RuntimeMode = "full",
    confirm: Callable[[], bool] | None = None,
) -> DoctorReport:
    health_url = hosted_origin.rstrip("/") + "/health"
    try:
        reachable = bool(getattr(http_get(health_url), "ok", False))
    except Exception:
        reachable = False
    decision = select_runtime_mode(probe, requested_mode)
    if decision.granted_mode == "analysis_only":
        print("Analysis-only mode disables:")
        for feature in decision.disabled_features:
            print(f"  - {feature}")
        if confirm is not None and not confirm():
            raise RuntimeError("analysis-only was not confirmed")
    return DoctorReport(
        control_plane_reachable=reachable,
        paired=paired,
        model_key_present=model_key_present,
        port_available=not port_in_use,
        disk_ok=free_disk_bytes >= MIN_FREE_DISK_BYTES,
        granted_mode=decision.granted_mode,
        downgraded=decision.downgraded,
        disabled_features=decision.disabled_features,
    )
