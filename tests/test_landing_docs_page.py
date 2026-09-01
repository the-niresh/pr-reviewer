"""Proves the docs page covers install, GitHub connect, BYOK, and the agent plugin (Task 21.2)."""

from __future__ import annotations

from pathlib import Path

DOCS_PAGE = (
    Path(__file__).resolve().parent.parent / "apps" / "web" / "src" / "app" / "docs" / "page.tsx"
)

REQUIRED_TOPICS = ("Install", "GitHub connect", "Bring your own key", "agent plugin")


def test_docs_page_exists() -> None:
    assert DOCS_PAGE.is_file(), f"missing {DOCS_PAGE}"


def test_docs_page_covers_every_required_topic() -> None:
    text = DOCS_PAGE.read_text(encoding="utf-8")
    missing = [topic for topic in REQUIRED_TOPICS if topic not in text]
    assert missing == [], f"docs page is missing: {missing}"
