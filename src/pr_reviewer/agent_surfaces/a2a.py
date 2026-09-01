"""Agent2Agent surface for review agents."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from pr_reviewer.agent_surfaces.core import (
    AgentReviewRequest,
    AgentSurfaceCore,
    AgentSurfaceRefusal,
)


class A2AResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok", "refused", "error"]
    result: dict[str, Any] | list[dict[str, Any]] | None = None
    refusal: dict[str, str] | None = None
    error: str | None = None


class A2ASurface:
    def __init__(self, core: AgentSurfaceCore, *, url: str = "http://127.0.0.1:0/a2a") -> None:
        self._core = core
        self._url = url

    def agent_card(self) -> dict[str, Any]:
        return {
            "protocolVersion": "0.3.0",
            "name": "PR Reviewer",
            "description": (
                "Reviews GitHub pull requests and returns findings with remediation prompts."
            ),
            "url": self._url,
            "preferredTransport": "JSONRPC",
            "version": "1.0.0",
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "stateTransitionHistory": False,
            },
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
            "skills": [
                {
                    "id": "pr-review",
                    "name": "Pull request review",
                    "description": "Start a review or fetch findings and remediation prompts.",
                    "inputModes": ["application/json"],
                    "outputModes": ["application/json"],
                    "tags": ["github", "pull-request", "review"],
                }
            ],
        }

    def handle_json_rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "message/send":
            params = payload.get("params")
            if not isinstance(params, dict):
                return _json_rpc_error(request_id, -32602, "message/send params must be an object")
            try:
                task = self._handle_message_send(params)
            except ValueError as error:
                return _json_rpc_error(request_id, -32602, str(error))
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": task,
            }
        if method == "agent/getAuthenticatedExtendedCard":
            return {"jsonrpc": "2.0", "id": request_id, "result": self.agent_card()}
        return _json_rpc_error(request_id, -32601, f"unknown method: {method}")

    def _handle_message_send(self, params: dict[str, Any]) -> dict[str, Any]:
        message = params.get("message")
        if not isinstance(message, dict):
            raise ValueError("message/send requires a message object")
        try:
            request = _request_from_message(message)
            result = self._call_command(request["command"], request["arguments"])
        except AgentSurfaceRefusal as refusal:
            payload = A2AResult(status="refused", refusal=refusal.as_payload()).model_dump(
                exclude_none=True
            )
            return _task(message, state="rejected", payload=payload)
        except (KeyError, TypeError, ValidationError, ValueError) as error:
            payload = A2AResult(status="error", error=str(error)).model_dump(exclude_none=True)
            return _task(message, state="failed", payload=payload)
        payload = A2AResult(status="ok", result=result).model_dump(exclude_none=True)
        return _task(message, state="completed", payload=payload)

    def _call_command(
        self,
        command: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if command == "review_pull_request":
            review = self._core.review_pull_request(AgentReviewRequest.model_validate(arguments))
            return review.model_dump(mode="json")
        if command == "list_findings":
            review_id = _required_string(arguments, "review_id")
            return [
                finding.model_dump(mode="json")
                for finding in self._core.list_findings(review_id)
            ]
        if command == "list_remediation_prompts":
            review_id = _required_string(arguments, "review_id")
            return [
                prompt.model_dump(mode="json")
                for prompt in self._core.list_remediation_prompts(review_id)
            ]
        raise ValueError(f"unknown A2A command: {command}")


def _request_from_message(message: dict[str, Any]) -> dict[str, Any]:
    for part in _message_parts(message):
        if not isinstance(part, dict):
            continue
        kind = part.get("kind", part.get("type"))
        if kind == "data" and isinstance(part.get("data"), dict):
            data = part["data"]
            command = data.get("command")
            arguments = data.get("arguments", {})
            if isinstance(command, str) and isinstance(arguments, dict):
                return {"command": command, "arguments": arguments}
    raise ValueError("message must include a data part with command and arguments")


def _message_parts(message: dict[str, Any]) -> list[Any]:
    parts = message.get("parts", message.get("content"))
    if not isinstance(parts, list):
        raise ValueError("message must include parts")
    return parts


def _task(message: dict[str, Any], *, state: str, payload: dict[str, Any]) -> dict[str, Any]:
    message_id = message.get("messageId")
    task_id = _task_id(message, payload)
    return {
        "id": task_id,
        "contextId": str(message.get("contextId") or task_id),
        "status": {"state": state},
        "artifacts": [
            {
                "artifactId": f"{task_id}-result",
                "name": "review-result",
                "parts": [{"kind": "data", "data": payload}],
            }
        ],
        "history": [message] if isinstance(message_id, str) and message_id else [],
    }


def _task_id(message: dict[str, Any], payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("review_id"), str):
        return cast(str, result["review_id"])
    message_id = message.get("messageId")
    if isinstance(message_id, str) and message_id:
        return f"review-request-{message_id}"
    return "review-request"


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _json_rpc_error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
