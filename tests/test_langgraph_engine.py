"""Failing tests for the LangGraph WorkflowEngine adapter (master Task 19).

Shared behaviour lives in test_workflow_engine.py and is parametrized over
both engines. This file asserts the adapter actually uses langgraph and stays
off by default. Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"


def test_langgraph_engine_is_disabled_by_default() -> None:
    from pr_reviewer.workflow.langgraph_engine import langgraph_engine_enabled

    assert langgraph_engine_enabled() is False


def test_langgraph_engine_module_imports_langgraph() -> None:
    source = (SRC_ROOT / "workflow" / "langgraph_engine.py").read_text(encoding="utf-8")
    assert "langgraph" in source
    from pr_reviewer.workflow.langgraph_engine import LangGraphEngine

    assert LangGraphEngine.__name__ == "LangGraphEngine"


def test_simple_engine_still_does_not_import_langgraph() -> None:
    source = (SRC_ROOT / "workflow" / "simple_engine.py").read_text(encoding="utf-8")
    assert "langgraph" not in source.lower()
