"""Every return_to the web app sends to /api/auth/github/sign-in must be one of the two
paths github_oauth.py's ALLOWED_RETURN_TO_PATHS actually accepts.

/dashboard/profile, /dashboard/settings, and a per-review /dashboard/reviews/{id} path were
all passed as returnTo values before this, none of them allowlisted -- clicking "Sign in
with GitHub" on any of those pages hit GET /api/auth/github/sign-in, which rejects an
unlisted return_to with a 400 (github_oauth.py's begin_sign_in). This walks every .tsx file
so a future page cannot reintroduce the same dead end, and it is driven off the real
allowlist rather than a copy of it, so it can never drift out of sync.
"""

from __future__ import annotations

import re
from pathlib import Path

from pr_reviewer.control_plane.github_oauth import ALLOWED_RETURN_TO_PATHS

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"

# A plain string literal: returnTo="/dashboard" or returnTo={"/dashboard"}.
RETURN_TO_LITERAL = re.compile(r"returnTo=\{?\"([^\"]+)\"\}?")
# A template literal or any other expression form: returnTo={`...`} or returnTo={expr}.
# Anything dynamic here can produce a value outside the allowlist at runtime, which a
# string-literal scan cannot verify, so it is banned outright rather than inspected.
RETURN_TO_DYNAMIC = re.compile(r"returnTo=\{(?!\"[^\"]+\"\})[^}]*\}")


def _tsx_files() -> list[Path]:
    return sorted(WEB_SRC.rglob("*.tsx"))


def test_at_least_one_file_uses_return_to() -> None:
    found = any(RETURN_TO_LITERAL.search(path.read_text(encoding="utf-8")) for path in _tsx_files())
    assert found, "no returnTo= usage found anywhere under apps/web/src -- has SignInPrompt moved?"


def test_no_file_passes_a_dynamic_return_to() -> None:
    offenders = []
    for path in _tsx_files():
        text = path.read_text(encoding="utf-8")
        for match in RETURN_TO_DYNAMIC.finditer(text):
            offenders.append(f"{path.relative_to(WEB_SRC)}: returnTo={match.group(0)[9:]}")
    assert offenders == [], f"dynamic (non-literal) returnTo value(s): {offenders}"


def test_every_literal_return_to_is_in_the_hosted_allowlist() -> None:
    offenders = []
    for path in _tsx_files():
        text = path.read_text(encoding="utf-8")
        for match in RETURN_TO_LITERAL.finditer(text):
            value = match.group(1)
            if value not in ALLOWED_RETURN_TO_PATHS:
                offenders.append(f"{path.relative_to(WEB_SRC)}: returnTo={value!r}")
    assert offenders == [], (
        f"returnTo value(s) not in ALLOWED_RETURN_TO_PATHS {sorted(ALLOWED_RETURN_TO_PATHS)}: "
        f"{offenders}"
    )


def test_the_literal_pattern_actually_catches_a_violation() -> None:
    match = RETURN_TO_LITERAL.search('<SignInPrompt returnTo="/dashboard/profile" />')
    assert match is not None
    assert match.group(1) == "/dashboard/profile"
    assert "/dashboard/profile" not in ALLOWED_RETURN_TO_PATHS


def test_the_dynamic_pattern_actually_catches_a_violation() -> None:
    assert RETURN_TO_DYNAMIC.search("<SignInPrompt returnTo={`/dashboard/reviews/${id}`} />")
    assert not RETURN_TO_DYNAMIC.search('<SignInPrompt returnTo="/dashboard" />')
