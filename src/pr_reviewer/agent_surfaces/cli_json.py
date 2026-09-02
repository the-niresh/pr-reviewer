"""Stable JSON command surface for agent clients."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, Literal, Never, TextIO

from pydantic import BaseModel, ConfigDict

from pr_reviewer.agent_surfaces.core import (
    AgentReviewRequest,
    AgentSurfaceCore,
    AgentSurfaceRefusal,
)


class JSONCLIResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok", "refused", "error"]
    result: dict[str, Any] | list[dict[str, Any]] | None = None
    refusal: dict[str, str] | None = None
    error: str | None = None


class _JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


class JSONCLI:
    def __init__(self, core: AgentSurfaceCore) -> None:
        self._core = core

    def main(
        self,
        argv: Sequence[str] | None = None,
        *,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> int:
        del stderr
        output = stdout or sys.stdout
        args = list(sys.argv[1:] if argv is None else argv)
        try:
            result = self.run(args)
        except AgentSurfaceRefusal as refusal:
            write_json_result(
                output,
                JSONCLIResult(status="refused", refusal=refusal.as_payload()),
            )
            return 2
        except (KeyError, TypeError, ValueError) as error:
            write_json_result(output, JSONCLIResult(status="error", error=str(error)))
            return 1
        write_json_result(output, JSONCLIResult(status="ok", result=result))
        return 0

    def run(self, argv: Sequence[str]) -> dict[str, Any] | list[dict[str, Any]]:
        namespace = _parser().parse_args(list(argv))
        command = namespace.command
        if command == "review":
            review = self._core.review_pull_request(
                AgentReviewRequest(
                    owner=namespace.owner,
                    repository=namespace.repository,
                    pull_request=namespace.pull_request,
                )
            )
            return review.model_dump(mode="json")
        if command == "findings":
            return [
                finding.model_dump(mode="json")
                for finding in self._core.list_findings(namespace.review_id)
            ]
        if command == "remediation-prompts":
            return [
                prompt.model_dump(mode="json")
                for prompt in self._core.list_remediation_prompts(namespace.review_id)
            ]
        raise ValueError(f"unknown JSON CLI command: {command}")


def _parser() -> argparse.ArgumentParser:
    parser = _JSONArgumentParser(prog="reviewer agent-json", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    review = subparsers.add_parser("review", add_help=False)
    review.add_argument("--owner", required=True)
    review.add_argument("--repository", required=True)
    review.add_argument("--pull-request", required=True, type=int)

    findings = subparsers.add_parser("findings", add_help=False)
    findings.add_argument("--review-id", required=True)

    prompts = subparsers.add_parser("remediation-prompts", add_help=False)
    prompts.add_argument("--review-id", required=True)

    return parser


def write_json_result(output: TextIO, payload: JSONCLIResult) -> None:
    print(
        json.dumps(payload.model_dump(mode="json", exclude_none=True), sort_keys=True),
        file=output,
    )
