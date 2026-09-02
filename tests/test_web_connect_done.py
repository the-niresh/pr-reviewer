"""Task 33.C2: the done screen sends the user back to the terminal.

Shown once repository permission is granted. One sentence, no next action on the web,
because there is not one.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
DONE_PAGE = WEB_SRC / "app" / "connect" / "done" / "page.tsx"

ACTION_ELEMENT = re.compile(r"<a\b|<button\b|<Link\b|href=", re.IGNORECASE)


def test_done_page_exists() -> None:
    assert DONE_PAGE.is_file(), f"missing {DONE_PAGE}"


def test_done_page_has_no_next_action() -> None:
    text = DONE_PAGE.read_text(encoding="utf-8")
    offenders = ACTION_ELEMENT.findall(text)
    assert offenders == [], f"done page offers a next action, but there is not one: {offenders}"


def test_done_page_tells_the_user_to_return_to_the_terminal() -> None:
    text = DONE_PAGE.read_text(encoding="utf-8").lower()
    assert "terminal" in text, "done page never mentions going back to the terminal"
    assert "finish" in text or "done" in text or "set" in text, (
        "done page never says the setup is finished"
    )
