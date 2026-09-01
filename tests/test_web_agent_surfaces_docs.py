"""Phase 28: install docs for each of the four agent surfaces (MCP, JSON CLI, ACP, A2A).

Checks the docs page's claims against the real surface source, not just that words appear on
the page: every tool/command/action name it prints must exist in the code that implements it.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WEB_SRC = REPO / "apps" / "web" / "src"
AGENTS_PAGE = WEB_SRC / "app" / "docs" / "agents" / "page.tsx"
DOCS_PAGE = WEB_SRC / "app" / "docs" / "page.tsx"
AGENT_SURFACES_SRC = REPO / "src" / "pr_reviewer" / "agent_surfaces"

REQUIRED_SURFACES = ("MCP", "JSON CLI", "ACP", "A2A")
REQUIRED_OPERATIONS = ("review_pull_request", "list_findings", "list_remediation_prompts")


def test_agents_docs_page_exists() -> None:
    assert AGENTS_PAGE.is_file(), f"missing {AGENTS_PAGE}"


def test_agents_docs_page_covers_all_four_surfaces() -> None:
    text = AGENTS_PAGE.read_text(encoding="utf-8")
    missing = [surface for surface in REQUIRED_SURFACES if surface not in text]
    assert missing == [], f"agent surfaces docs page is missing: {missing}"


def test_agents_docs_page_operation_names_exist_in_the_real_core() -> None:
    page_text = AGENTS_PAGE.read_text(encoding="utf-8")
    core_text = (AGENT_SURFACES_SRC / "core.py").read_text(encoding="utf-8")
    for operation in REQUIRED_OPERATIONS:
        assert operation in page_text, f"docs page never mentions {operation}"
        assert f"def {operation}" in core_text, (
            f"docs page claims {operation} exists, but core.py has no such method"
        )


def test_parent_docs_page_links_to_the_agent_surfaces_page() -> None:
    text = DOCS_PAGE.read_text(encoding="utf-8")
    assert "/docs/agents" in text, "docs page has no link to /docs/agents"
