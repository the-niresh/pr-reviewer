from __future__ import annotations

import json
from io import StringIO
from typing import Any, cast

from pr_reviewer.agent_surfaces.a2a import A2ASurface
from pr_reviewer.agent_surfaces.acp import ACPSurface
from pr_reviewer.agent_surfaces.cli_json import JSONCLI
from pr_reviewer.agent_surfaces.core import (
    AgentReviewRequest,
    AgentSurfaceCore,
    GitHubConnectionState,
    RemediationPrompt,
    SurfaceFinding,
    SurfaceReview,
    remediation_prompt_for_finding,
)
from pr_reviewer.agent_surfaces.mcp_server import MCPServer


def _finding() -> SurfaceFinding:
    return SurfaceFinding(
        id="finding-1",
        concern="correctness",
        severity="high",
        category="null-check",
        file_path="app.py",
        line_start=12,
        line_end=12,
        title="Missing null check",
        rationale="value can be None before it is used.",
        evidence=("app.py:12",),
        confidence=0.82,
    )


class FakeBackend:
    def __init__(
        self,
        *,
        connected: bool = True,
        raise_error: BaseException | None = None,
    ) -> None:
        self.connected = connected
        self.raise_error = raise_error
        self.findings = (_finding(),)
        self.prompts = tuple(remediation_prompt_for_finding(finding) for finding in self.findings)

    def github_connection_state(self) -> GitHubConnectionState:
        return GitHubConnectionState(
            connected=self.connected,
            reason=None if self.connected else "GitHub is not connected.",
        )

    def start_review(self, request: AgentReviewRequest) -> SurfaceReview:
        assert request == AgentReviewRequest(owner="acme", repository="widgets", pull_request=12)
        if self.raise_error is not None:
            raise self.raise_error
        return SurfaceReview(
            review_id="review-1",
            owner=request.owner,
            repository=request.repository,
            pull_request=request.pull_request,
            head_sha="deadbeef00000000000000000000000000000000",
            status="complete",
            findings=self.findings,
            remediation_prompts=self.prompts,
        )

    def list_findings(self, review_id: str) -> tuple[SurfaceFinding, ...]:
        assert review_id == "review-1"
        return self.findings

    def list_remediation_prompts(self, review_id: str) -> tuple[RemediationPrompt, ...]:
        assert review_id == "review-1"
        return self.prompts


def _core(
    *,
    connected: bool = True,
    raise_error: BaseException | None = None,
) -> AgentSurfaceCore:
    return AgentSurfaceCore(FakeBackend(connected=connected, raise_error=raise_error))


def _cli_payload(
    argv: list[str],
    *,
    connected: bool = True,
    raise_error: BaseException | None = None,
) -> dict[str, Any]:
    stdout = StringIO()
    JSONCLI(_core(connected=connected, raise_error=raise_error)).main(
        argv,
        stdout=stdout,
        stderr=StringIO(),
    )
    return cast(dict[str, Any], json.loads(stdout.getvalue()))


def _a2a_payload(
    command: str,
    arguments: dict[str, object],
    *,
    connected: bool = True,
    raise_error: BaseException | None = None,
) -> dict[str, Any]:
    response = A2ASurface(_core(connected=connected, raise_error=raise_error)).handle_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": "message-1",
                    "parts": [
                        {
                            "kind": "data",
                            "data": {"command": command, "arguments": arguments},
                        }
                    ],
                }
            },
        }
    )
    task = cast(dict[str, Any], response["result"])
    artifact = cast(dict[str, Any], cast(list[object], task["artifacts"])[0])
    part = cast(dict[str, Any], cast(list[object], artifact["parts"])[0])
    return cast(dict[str, Any], part["data"])


def _review_payloads(
    *,
    connected: bool = True,
    raise_error: BaseException | None = None,
) -> list[dict[str, Any]]:
    arguments: dict[str, object] = {
        "owner": "acme",
        "repository": "widgets",
        "pull_request": 12,
    }
    return [
        MCPServer(_core(connected=connected, raise_error=raise_error)).call_tool(
            "review_pull_request",
            arguments,
        ),
        _cli_payload(
            [
                "review",
                "--owner",
                "acme",
                "--repository",
                "widgets",
                "--pull-request",
                "12",
            ],
            connected=connected,
            raise_error=raise_error,
        ),
        ACPSurface(_core(connected=connected, raise_error=raise_error)).call_action(
            "review_pull_request",
            arguments,
        ),
        _a2a_payload(
            "review_pull_request",
            arguments,
            connected=connected,
            raise_error=raise_error,
        ),
    ]


def _findings_payloads() -> list[dict[str, Any]]:
    arguments: dict[str, object] = {"review_id": "review-1"}
    return [
        MCPServer(_core()).call_tool("list_findings", arguments),
        _cli_payload(["findings", "--review-id", "review-1"]),
        ACPSurface(_core()).call_action("list_findings", arguments),
        _a2a_payload("list_findings", arguments),
    ]


def _remediation_payloads() -> list[dict[str, Any]]:
    arguments: dict[str, object] = {"review_id": "review-1"}
    return [
        MCPServer(_core()).call_tool("list_remediation_prompts", arguments),
        _cli_payload(["remediation-prompts", "--review-id", "review-1"]),
        ACPSurface(_core()).call_action("list_remediation_prompts", arguments),
        _a2a_payload("list_remediation_prompts", arguments),
    ]


def test_all_agent_surfaces_return_the_same_review_payload() -> None:
    payloads = _review_payloads()

    assert payloads == [payloads[0]] * 4
    assert payloads[0]["result"]["review_id"] == "review-1"
    assert payloads[0]["result"]["findings"][0]["id"] == "finding-1"


def test_all_agent_surfaces_return_the_same_finding_and_prompt_payloads() -> None:
    finding_payloads = _findings_payloads()
    prompt_payloads = _remediation_payloads()

    assert finding_payloads == [finding_payloads[0]] * 4
    assert prompt_payloads == [prompt_payloads[0]] * 4
    assert prompt_payloads[0]["result"][0]["finding_id"] == "finding-1"


def test_all_agent_surfaces_refuse_without_github_the_same_way() -> None:
    payloads = _review_payloads(connected=False)

    assert payloads == [payloads[0]] * 4
    assert payloads[0] == {
        "status": "refused",
        "refusal": {
            "code": "github_not_connected",
            "message": "GitHub is not connected. Connect GitHub before requesting a review.",
            "action": "Connect GitHub, then retry the request.",
        },
    }


def test_all_agent_surfaces_report_unexpected_errors_the_same_structured_way() -> None:
    payloads = _review_payloads(
        raise_error=RuntimeError("boom\nTraceback raw provider payload")
    )

    assert payloads == [payloads[0]] * 4
    assert payloads[0] == {
        "status": "error",
        "error": {
            "code": "unexpected_error",
            "message": "Review failed unexpectedly.",
            "action": "Check the local logs, fix the cause, then retry the request.",
        },
    }
    assert "Traceback" not in json.dumps(payloads)
    assert "boom" not in json.dumps(payloads)
