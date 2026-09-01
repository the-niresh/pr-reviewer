"""Agent Client Protocol surface for review clients."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pr_reviewer.agent_surfaces.core import (
    AgentReviewRequest,
    AgentSurfaceCore,
    AgentSurfaceRefusal,
)


class ACPAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: dict[str, Any]


class ACPResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok", "refused", "error"]
    result: dict[str, Any] | list[dict[str, Any]] | None = None
    refusal: dict[str, str] | None = None
    error: str | None = None


_ACTIONS: tuple[ACPAction, ...] = (
    ACPAction(
        name="review_pull_request",
        description="Start a PR review and return the review, findings and remediation prompts.",
        input_schema=AgentReviewRequest.model_json_schema(),
    ),
    ACPAction(
        name="list_findings",
        description="List findings for a review id.",
        input_schema={
            "type": "object",
            "properties": {"review_id": {"type": "string", "minLength": 1}},
            "required": ["review_id"],
            "additionalProperties": False,
        },
    ),
    ACPAction(
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


class ACPSurface:
    def __init__(self, core: AgentSurfaceCore) -> None:
        self._core = core

    def initialize(self) -> dict[str, Any]:
        return {
            "protocol": "acp",
            "version": "1",
            "actions": self.list_actions(),
        }

    def list_actions(self) -> list[dict[str, Any]]:
        return [action.model_dump(mode="json") for action in _ACTIONS]

    def call_action(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._call_action(name, arguments)
        except AgentSurfaceRefusal as refusal:
            return ACPResult(status="refused", refusal=refusal.as_payload()).model_dump(
                exclude_none=True
            )
        except (KeyError, TypeError, ValidationError, ValueError) as error:
            return ACPResult(status="error", error=str(error)).model_dump(exclude_none=True)
        return ACPResult(status="ok", result=result).model_dump(exclude_none=True)

    def handle_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params")
        if method == "initialize":
            return {"id": request_id, "result": self.initialize()}
        if method == "actions/list":
            return {"id": request_id, "result": {"actions": self.list_actions()}}
        if method == "actions/call":
            if not isinstance(params, dict):
                return _message_error(request_id, "actions/call params must be an object")
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return _message_error(request_id, "actions/call requires name and arguments")
            return {
                "id": request_id,
                "result": self.call_action(name, arguments),
            }
        return _message_error(request_id, f"unknown method: {method}")

    def _call_action(
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
        raise ValueError(f"unknown ACP action: {name}")


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _message_error(request_id: object, message: str) -> dict[str, Any]:
    return {"id": request_id, "error": {"code": "invalid_request", "message": message}}
