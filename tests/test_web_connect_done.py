"""Task 33.C2, revised: the done screen sends the user back to the terminal, then on to the
dashboard.

The owner asked for this explicitly: after a successful sign-in the page should tell the
user to go to the terminal, count down five seconds, then redirect to /dashboard, with an
immediate link for anyone who does not want to wait. That is a real next action, so the
old "no action element at all" guard no longer matches the product: it is replaced with
checks that the redirect target and the countdown are actually present, and that the
countdown component respects prefers-reduced-motion rather than forcing an animation on
everyone.
"""

from __future__ import annotations

from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
DONE_PAGE = WEB_SRC / "app" / "connect" / "done" / "page.tsx"
COUNTDOWN_COMPONENT = WEB_SRC / "components" / "ConnectDoneCountdown.tsx"


def test_done_page_exists() -> None:
    assert DONE_PAGE.is_file(), f"missing {DONE_PAGE}"


def test_countdown_component_exists() -> None:
    assert COUNTDOWN_COMPONENT.is_file(), f"missing {COUNTDOWN_COMPONENT}"


def test_done_page_tells_the_user_to_return_to_the_terminal() -> None:
    text = DONE_PAGE.read_text(encoding="utf-8").lower()
    assert "terminal" in text, "done page never mentions going back to the terminal"
    assert "finish" in text or "done" in text or "set" in text, (
        "done page never says the setup is finished"
    )


def test_countdown_redirects_to_the_dashboard() -> None:
    text = COUNTDOWN_COMPONENT.read_text(encoding="utf-8")
    assert '"/dashboard"' in text, "countdown never names /dashboard as its redirect target"
    assert "router.push" in text, "countdown never actually calls the redirect"


def test_countdown_gives_an_immediate_way_out() -> None:
    text = COUNTDOWN_COMPONENT.read_text(encoding="utf-8")
    assert "<Link" in text, (
        "countdown offers no immediate link, trapping anyone who does not want to wait"
    )


def test_countdown_respects_reduced_motion() -> None:
    text = COUNTDOWN_COMPONENT.read_text(encoding="utf-8")
    assert "motion-reduce:" in text, "countdown's progress animation ignores prefers-reduced-motion"
