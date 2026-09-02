"""Task 33.C1: after sign-in, the connect page asks only for repository permission.

The web is deliberately thin: one card, one action, choose repositories on GitHub. No key
field, no settings, no model picker. This enumerates the page's inputs and its one action,
and fails if anything exists that is not the repository step.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
CONNECT_PAGE = WEB_SRC / "app" / "connect" / "page.tsx"

INPUT_TAG = re.compile(r"<input\b", re.IGNORECASE)
ANCHOR_TAG = re.compile(r"<a\b", re.IGNORECASE)
FORBIDDEN_TERMS = re.compile(
    r"model key|api key|provider key|settings|subscription|password",
    re.IGNORECASE,
)


def test_connect_page_exists() -> None:
    assert CONNECT_PAGE.is_file(), f"missing {CONNECT_PAGE}"


def test_connect_page_has_no_input_elements() -> None:
    text = CONNECT_PAGE.read_text(encoding="utf-8")
    offenders = INPUT_TAG.findall(text)
    assert offenders == [], (
        f"connect page renders {len(offenders)} <input> element(s); "
        "it must ask for nothing but repository permission"
    )


def test_connect_page_offers_exactly_one_action_and_it_targets_github() -> None:
    text = CONNECT_PAGE.read_text(encoding="utf-8")
    anchors = ANCHOR_TAG.findall(text)
    assert len(anchors) == 1, f"expected exactly one action element, found {len(anchors)}"
    assert "github.com" in text, "the one action must point at GitHub"


def test_connect_page_names_no_action_other_than_repository_permission() -> None:
    text = CONNECT_PAGE.read_text(encoding="utf-8")
    offenders = FORBIDDEN_TERMS.findall(text)
    assert offenders == [], f"connect page mentions a non-repository action: {offenders}"
