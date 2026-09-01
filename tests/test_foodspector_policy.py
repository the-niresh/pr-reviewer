"""FoodSpector shadow policy refusals. Each case fails for a distinct reason."""

from __future__ import annotations

from pathlib import Path

import pytest

from pr_reviewer.foodspector_policy import (
    PER_PR_BUDGET_CAP_USD,
    ShadowPolicyRefused,
    assert_shadow_policy_allowed,
    load_shadow_policy,
)
from pr_reviewer.jobs.enqueue_review_job import DEFAULT_BUDGET_MAX_COST_USD

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "config" / "food-spector.policy.example.toml"
LISTED = "the-niresh/FoodSpector"


def _write_policy(
    path: Path,
    *,
    auto_post: bool = False,
    allowlist: tuple[str, ...] = (LISTED,),
    kill_switch: bool | None = False,
    per_pr_budget_usd: str = "1.000000",
) -> Path:
    lines = [
        f"auto_post = {'true' if auto_post else 'false'}",
        "repository_allowlist = [" + ", ".join(f'"{item}"' for item in allowlist) + "]",
        f'per_pr_budget_usd = "{per_pr_budget_usd}"',
    ]
    if kill_switch is not None:
        lines.insert(1, f"kill_switch = {'true' if kill_switch else 'false'}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_budget_cap_matches_enqueue_default() -> None:
    assert PER_PR_BUDGET_CAP_USD == DEFAULT_BUDGET_MAX_COST_USD


def test_auto_post_before_release_gates_is_refused(tmp_path: Path) -> None:
    policy = load_shadow_policy(_write_policy(tmp_path / "policy.toml", auto_post=True))
    with pytest.raises(ShadowPolicyRefused) as exc:
        assert_shadow_policy_allowed(policy, repository=LISTED, release_gates_passed=False)
    assert exc.value.reason == "auto_post_before_release_gates"


def test_repository_outside_allowlist_is_refused(tmp_path: Path) -> None:
    policy = load_shadow_policy(_write_policy(tmp_path / "policy.toml"))
    with pytest.raises(ShadowPolicyRefused) as exc:
        assert_shadow_policy_allowed(policy, repository="someone/else", release_gates_passed=False)
    assert exc.value.reason == "repository_not_allowlisted"


def test_missing_kill_switch_is_refused(tmp_path: Path) -> None:
    path = _write_policy(tmp_path / "policy.toml", kill_switch=None)
    with pytest.raises(ShadowPolicyRefused) as exc:
        load_shadow_policy(path)
    assert exc.value.reason == "missing_kill_switch"


def test_per_pr_budget_above_cap_is_refused(tmp_path: Path) -> None:
    policy = load_shadow_policy(
        _write_policy(tmp_path / "policy.toml", per_pr_budget_usd="1.000001")
    )
    with pytest.raises(ShadowPolicyRefused) as exc:
        assert_shadow_policy_allowed(policy, repository=LISTED, release_gates_passed=False)
    assert exc.value.reason == "per_pr_budget_over_cap"


def test_example_policy_allows_listed_repo_with_auto_post_off() -> None:
    policy = load_shadow_policy(EXAMPLE)
    assert policy.auto_post is False
    assert_shadow_policy_allowed(policy, repository=LISTED, release_gates_passed=False)
