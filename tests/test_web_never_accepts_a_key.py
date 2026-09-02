"""Task 33.C3: standing guard - no hosted route ever accepts a provider key.

Walks every route under apps/web/src/app and fails if any renders a password input, or
posts to a path containing "model-key". This is not a one-time check: it must fail the
day someone adds a key field to any future page, not just today's pages.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_APP = Path(__file__).resolve().parent.parent / "apps" / "web" / "src" / "app"

PASSWORD_INPUT = re.compile(r"<input\b[^>]*\btype=[\"'{]*password", re.IGNORECASE)
MODEL_KEY_PATH = re.compile(r"model-key", re.IGNORECASE)


def _pages() -> list[Path]:
    return sorted(WEB_APP.rglob("page.tsx"))


def test_at_least_one_route_is_scanned() -> None:
    # A guard over zero files proves nothing; this fails loudly if the app directory
    # ever moves or empties out from under this test.
    assert _pages(), f"no page.tsx files found under {WEB_APP}"


def test_no_route_renders_a_password_input() -> None:
    offenders = [
        str(page.relative_to(WEB_APP))
        for page in _pages()
        if PASSWORD_INPUT.search(page.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"password input found on: {offenders}"


def test_no_route_posts_to_a_model_key_path() -> None:
    offenders = [
        str(page.relative_to(WEB_APP))
        for page in _pages()
        if MODEL_KEY_PATH.search(page.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"model-key path referenced on: {offenders}"


def test_the_password_pattern_actually_catches_a_violation() -> None:
    # A guard that can never turn red proves nothing. Every real page.tsx passes today, so
    # this proves the pattern against a known-bad snippet instead of a real page.
    assert PASSWORD_INPUT.search('<input type="password" name="key" />')
    assert not PASSWORD_INPUT.search('<input type="text" name="repository" />')


def test_the_model_key_path_pattern_actually_catches_a_violation() -> None:
    assert MODEL_KEY_PATH.search('fetch("/api/model-key", { method: "POST" })')
    assert not MODEL_KEY_PATH.search('fetch("/api/reviews")')
