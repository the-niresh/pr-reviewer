"""Task 33.C3: the /dashboard overview must read at a glance and never blur "no reviews
yet" into "could not load".

Follows test_web_out_of_tokens.py's shape: the API-level behaviour is proven against the
real control plane, and the page's own source is guarded the way test_web_never_accepts_a_key.py
guards other pages, so a regression in the component -- not just the payload -- turns a test
red too. Rendering Next.js server components is out of reach for pytest, so the page checks
here are structural: they name the exact lines that must exist and the exact confusion
(empty and broken sharing one branch) that must not.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
DASHBOARD_PAGE = WEB_SRC / "app" / "dashboard" / "page.tsx"
DASHBOARD_SHELL = WEB_SRC / "components" / "DashboardShell.tsx"
DASHBOARD_STATE = WEB_SRC / "components" / "DashboardState.tsx"
SEVERITY_BREAKDOWN = WEB_SRC / "components" / "SeverityBreakdown.tsx"
REVIEWS_LIB = WEB_SRC / "lib" / "reviews.ts"


def test_dashboard_page_exists() -> None:
    assert DASHBOARD_PAGE.is_file(), f"missing {DASHBOARD_PAGE}"


def test_dashboard_handles_all_three_outcomes_distinctly() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    assert '"unauthenticated"' in source, "dashboard never checks for the signed-out case"
    assert '"error"' in source, "dashboard never checks for a load failure"
    assert "reviews.length === 0" in source, "dashboard never checks for a real empty state"


def test_no_reviews_and_could_not_load_are_different_components() -> None:
    """The exact confusion the task calls out by name: an empty dashboard must never
    render through the same branch, or the same words, as a broken one."""
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    assert "No reviews yet" in source
    assert "<LoadError" in source
    # LoadError must not also be what renders under the empty-state branch.
    empty_state_start = source.index("No reviews yet")
    load_error_start = source.index("<LoadError")
    assert not (load_error_start < empty_state_start < load_error_start + 200), (
        "the empty state and the load-error state must not be the same rendered block"
    )


def test_severity_breakdown_uses_semantic_colour_not_the_brand_accent() -> None:
    source = SEVERITY_BREAKDOWN.read_text(encoding="utf-8")
    assert "danger" in source and "warning" in source and "muted" in source
    # "default" is the brand-accent badge variant (badge.tsx); severity must never use it.
    assert re.search(r'variant:\s*"default"', source) is None
    assert 'Record<SeverityLevel, "danger" | "warning" | "muted">' in source


def test_dashboard_uses_the_severity_breakdown_component() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    assert "<SeverityBreakdown" in source


def test_dashboard_shows_recent_reviews_linking_to_the_single_review_page() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    assert "/dashboard/reviews/${review.review_job_id}" in source


def test_dashboard_never_shows_a_stopped_early_review_as_a_plain_severity_badge() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    assert "review.stopped_early" in source
    assert "Stopped early" in source


def test_load_error_and_sign_in_prompt_are_visually_and_textually_distinct() -> None:
    source = DASHBOARD_STATE.read_text(encoding="utf-8")
    assert "Could not load" in source
    assert "Sign in" in source
    assert "destructive" in source, "a load failure must carry a distinct, non-neutral colour"


def test_fetch_reviews_distinguishes_unauthenticated_error_and_ok() -> None:
    source = REVIEWS_LIB.read_text(encoding="utf-8")
    for kind in ('"unauthenticated"', '"error"', '"ok"'):
        assert kind in source, f"fetchReviews never returns the {kind} outcome"


def test_dashboard_nav_marks_the_current_page_with_aria_current() -> None:
    """Design rule: any nav with a notion of "current" must mark it with aria-current,
    not rely on hover alone. Profile and Settings join this nav in a later task; this only
    guards that the mechanism (aria-current, not hover-only) is there from the start."""
    source = DASHBOARD_SHELL.read_text(encoding="utf-8")
    assert "aria-current" in source
    assert '"/dashboard"' in source
    assert '"/dashboard/reviews"' in source
