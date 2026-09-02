"""The agent surfaces (agent_surfaces/*.py) are useless if nothing outside the package can reach
them. This asserts the `reviewer` router actually dispatches to each one -- not just that the
usage string mentions the word, but that calling `reviewer <name>` really calls that subcommand's
`main`. Breaking any one branch in reviewer_entry.py must fail exactly one of these tests.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from typing import Any

import pytest


def _fake_main(calls: list[Sequence[str]], return_code: int = 0) -> Any:
    def fake(argv: Sequence[str] | None = None, **kwargs: object) -> int:
        del kwargs
        calls.append(list(argv or []))
        return return_code

    return fake


def test_reviewer_routes_mcp_to_runner_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.reviewer_entry import main as reviewer_main

    calls: list[Sequence[str]] = []
    monkeypatch.setattr("pr_reviewer.runner.cli.mcp.main", _fake_main(calls, 0))

    code = reviewer_main(["mcp", "--stdio"])

    assert code == 0
    assert calls == [["--stdio"]]


def test_reviewer_routes_a2a_to_runner_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.reviewer_entry import main as reviewer_main

    calls: list[Sequence[str]] = []
    monkeypatch.setattr("pr_reviewer.runner.cli.a2a.main", _fake_main(calls, 0))

    code = reviewer_main(["a2a"])

    assert code == 0
    assert calls == [[]]


def test_reviewer_routes_acp_to_runner_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.reviewer_entry import main as reviewer_main

    calls: list[Sequence[str]] = []
    monkeypatch.setattr("pr_reviewer.runner.cli.acp.main", _fake_main(calls, 0))

    code = reviewer_main(["acp"])

    assert code == 0
    assert calls == [[]]


def test_reviewer_routes_review_to_runner_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from pr_reviewer.reviewer_entry import main as reviewer_main

    calls: list[Sequence[str]] = []
    monkeypatch.setattr("pr_reviewer.runner.cli.review.main", _fake_main(calls, 7))

    code = reviewer_main(["review", "acme/widgets#1", "--json"])

    assert code == 7
    assert calls == [["acme/widgets#1", "--json"]]


def test_usage_lists_every_agent_surface_subcommand() -> None:
    from pr_reviewer.reviewer_entry import _USAGE

    for name in ("review", "mcp", "a2a", "acp"):
        assert name in _USAGE


def test_mcp_main_serves_a_real_backend_over_stdio() -> None:
    """Runs the actual `reviewer mcp` main(), not a fake, end to end over stdio.

    tools/list never touches GitHub or a model provider, so this proves the stdio loop and the
    real LiveAgentReviewBackend wiring both work without any network access.
    """
    from pr_reviewer.runner.cli.mcp import main as mcp_main

    request = {"jsonrpc": "2.0", "id": "1", "method": "tools/list"}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    code = mcp_main([], stdin=stdin, stdout=stdout)

    assert code == 0
    response = json.loads(stdout.getvalue())
    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert "review_pull_request" in tool_names


def test_a2a_main_serves_a_real_backend_over_stdio() -> None:
    from pr_reviewer.runner.cli.a2a import main as a2a_main

    request = {"jsonrpc": "2.0", "id": "1", "method": "agent/getAuthenticatedExtendedCard"}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    code = a2a_main([], stdin=stdin, stdout=stdout)

    assert code == 0
    response = json.loads(stdout.getvalue())
    assert response["result"]["name"] == "PR Reviewer"


def test_acp_main_serves_a_real_backend_over_stdio() -> None:
    from pr_reviewer.runner.cli.acp import main as acp_main

    request = {"id": "1", "method": "initialize"}
    stdin = io.StringIO(json.dumps(request) + "\n")
    stdout = io.StringIO()

    code = acp_main([], stdin=stdin, stdout=stdout)

    assert code == 0
    response = json.loads(stdout.getvalue())
    action_names = {action["name"] for action in response["result"]["actions"]}
    assert "review_pull_request" in action_names
