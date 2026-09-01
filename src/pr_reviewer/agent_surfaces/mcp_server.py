"""MCP-compatible tools for agent clients."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pr_reviewer.agent_surfaces.core import (
    AgentReviewRequest,
    AgentSurfaceCore,
    AgentSurfaceRefusal,
)


class MCPTool(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]


class MCPToolResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok", "refused", "error"]
    result: dict[str, Any] | list[dict[str, Any]] | None = None
    refusal: dict[str, str] | None = None
    error: str | None = None


_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="review_pull_request",
        description="Start a PR review and return the review, findings and remediation prompts.",
        input_schema=AgentReviewRequest.model_json_schema(),
    ),
    MCPTool(
        name="list_findings",
        description="List findings for a review id.",
        input_schema={
            "type": "object",
            "properties": {"review_id": {"type": "string", "minLength": 1}},
            "required": ["review_id"],
            "additionalProperties": False,
        },
    ),
    MCPTool(
        name="list_remediation_prompts",
        description="List remediation prompts for a review id.",
        input_schema={
            "type": "object",
            "properties": {"review_id": {"type": "string", "minLength": 1}},
            "required": ["review_id"],
            "additionalProperties": False,
        },
    ),
)


class MCPServer:
    def __init__(self, core: AgentSurfaceCore) -> None:
        self._core = core

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.model_dump(by_alias=True) for tool in _TOOLS]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._call_tool(name, arguments)
        except AgentSurfaceRefusal as refusal:
            return MCPToolResult(status="refused", refusal=refusal.as_payload()).model_dump(
                exclude_none=True
            )
        except (KeyError, TypeError, ValidationError, ValueError) as error:
            return MCPToolResult(status="error", error=str(error)).model_dump(exclude_none=True)
        return MCPToolResult(status="ok", result=result).model_dump(exclude_none=True)

    def handle_json_rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params")
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.list_tools()}}
        if method == "tools/call":
            if not isinstance(params, dict):
                return _json_rpc_error(request_id, "tools/call params must be an object")
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return _json_rpc_error(request_id, "tools/call requires name and arguments")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": self.call_tool(name, arguments),
            }
        return _json_rpc_error(request_id, f"unknown method: {method}")

    def _call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if name == "review_pull_request":
            review = self._core.review_pull_request(AgentReviewRequest.model_validate(arguments))
            return review.model_dump(mode="json")
        if name == "list_findings":
            review_id = _required_string(arguments, "review_id")
            return [
                finding.model_dump(mode="json")
                for finding in self._core.list_findings(review_id)
            ]
        if name == "list_remediation_prompts":
            review_id = _required_string(arguments, "review_id")
            return [
                prompt.model_dump(mode="json")
                for prompt in self._core.list_remediation_prompts(review_id)
            ]
        raise ValueError(f"unknown MCP tool: {name}")


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _json_rpc_error(request_id: object, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": message}}
