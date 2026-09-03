"""The onboarding page's "Sign in with GitHub" control must actually go somewhere.

It started life as `<a href="#">Sign in with GitHub</a>` (commit 443b358) and the shadcn
rebuild (db23d98) dropped even that placeholder, leaving a plain `<Button>` with no href
and no onClick -- a real dead end, not a stand-in. The local daemon already exposes
GET /onboarding/pairing/sign-in returning the hosted URL to send the browser to
(runner/web/local_auth.py); this page must fetch it and use it.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
ONBOARDING_PAGE = WEB_SRC / "app" / "onboarding" / "page.tsx"

DEAD_SIGN_IN_BUTTON = re.compile(
    r'<a\s+href="#"[^>]*>\s*(?:<GithubMark[^/]*/>\s*)?Sign in with GitHub'
)


def test_onboarding_page_exists() -> None:
    assert ONBOARDING_PAGE.is_file(), f"missing {ONBOARDING_PAGE}"


def test_onboarding_page_fetches_the_local_pairing_sign_in_url() -> None:
    source = ONBOARDING_PAGE.read_text(encoding="utf-8")
    assert "/onboarding/pairing/sign-in" in source, (
        "onboarding page never calls the local daemon's pairing sign-in endpoint"
    )


def test_onboarding_sign_in_button_becomes_a_real_link_once_the_url_is_known() -> None:
    """The fetched URL must actually reach the anchor's href, not just sit in state that
    nothing reads."""
    source = ONBOARDING_PAGE.read_text(encoding="utf-8")
    assert re.search(r"href=\{signInUrl\}", source), (
        "the fetched sign-in URL is never wired to an href"
    )


def test_onboarding_sign_in_is_disabled_rather_than_a_dead_link_while_unknown() -> None:
    """Before the daemon answers (or if it never does), the control must be visibly
    disabled -- never a clickable element that goes nowhere. The page renders the label
    twice (the real link once the URL is known, a disabled fallback until then); this
    checks the *last* one, which is the fallback, since a "disabled" prop belongs there,
    not on the real link."""
    source = ONBOARDING_PAGE.read_text(encoding="utf-8")
    button_start = source.rindex("Sign in with GitHub")
    preceding = source[max(0, button_start - 300) : button_start]
    assert "disabled" in preceding, "no disabled fallback found before the daemon answers"


def test_onboarding_page_has_no_placeholder_href(  # guards against a regression to "#"
) -> None:
    source = ONBOARDING_PAGE.read_text(encoding="utf-8")
    assert 'href="#"' not in source


def test_the_dead_button_pattern_actually_catches_a_violation() -> None:
    assert DEAD_SIGN_IN_BUTTON.search(
        '<a href="#"><GithubMark className="size-4" />Sign in with GitHub</a>'
    )
    assert not DEAD_SIGN_IN_BUTTON.search(
        '<a href={signInUrl}><GithubMark className="size-4" />Sign in with GitHub</a>'
    )
