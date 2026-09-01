"""FoodSpector shadow policy. Refuses unsafe settings before any deploy."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


class ShadowPolicyRefused(Exception):
    """A FoodSpector shadow policy setting is not allowed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


PER_PR_BUDGET_CAP_USD = Decimal("1.000000")


@dataclass(frozen=True)
class ShadowPolicy:
    auto_post: bool
    repository_allowlist: tuple[str, ...]
    kill_switch: bool
    per_pr_budget_usd: Decimal


def _as_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ShadowPolicyRefused(f"{field}_not_bool")
    return value


def load_shadow_policy(path: Path) -> ShadowPolicy:
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    if "kill_switch" not in data:
        raise ShadowPolicyRefused("missing_kill_switch")
    raw_allow = data.get("repository_allowlist") or []
    if not isinstance(raw_allow, list) or not all(isinstance(item, str) for item in raw_allow):
        raise ShadowPolicyRefused("repository_allowlist_invalid")
    budget_raw = data.get("per_pr_budget_usd", "0")
    budget = Decimal(str(budget_raw))
    return ShadowPolicy(
        auto_post=_as_bool(data.get("auto_post", False), "auto_post"),
        repository_allowlist=tuple(raw_allow),
        kill_switch=_as_bool(data["kill_switch"], "kill_switch"),
        per_pr_budget_usd=budget,
    )


def assert_shadow_policy_allowed(
    policy: ShadowPolicy,
    *,
    repository: str,
    release_gates_passed: bool,
) -> None:
    if policy.auto_post and not release_gates_passed:
        raise ShadowPolicyRefused("auto_post_before_release_gates")
    if repository not in policy.repository_allowlist:
        raise ShadowPolicyRefused("repository_not_allowlisted")
    if policy.per_pr_budget_usd > PER_PR_BUDGET_CAP_USD:
        raise ShadowPolicyRefused("per_pr_budget_over_cap")
