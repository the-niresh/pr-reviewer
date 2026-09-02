"""`reviewer review <owner/repo#pr>` -- the machine-readable review command.

Reuses agent_surfaces/cli_json.py for JSON serialization (JSONCLIResult, write_json_result)
instead of building a second serializer: this module only decides which exit code that JSON
earned, and whether a human summary or the raw JSON document reaches stdout. Under --json, stdout
carries exactly one JSON document and nothing else -- no banner, no progress, no colour; every
human-readable line goes to stderr instead.

Exit codes (also printed in --help):
  0  review completed, no findings
  1  review completed, findings present
  2  refused (a structured refusal -- e.g. GitHub not connected, provider out of tokens)
  3  the request or the run itself failed unexpectedly
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from pr_reviewer.agent_surfaces.backend import LiveAgentReviewBackend
from pr_reviewer.agent_surfaces.cli_json import JSONCLI, JSONCLIResult, write_json_result
from pr_reviewer.agent_surfaces.core import (
    AgentSurfaceCore,
    AgentSurfaceRefusal,
    agent_surface_error_payload,
)

EXIT_OK_NO_FINDINGS = 0
EXIT_OK_FINDINGS = 1
EXIT_REFUSED = 2
EXIT_ERROR = 3

_PULL_REQUEST_REF = re.compile(r"^(?P<owner>[^/#]+)/(?P<repository>[^/#]+)#(?P<number>\d+)$")

_EPILOG = """\
JSON output under --json:
  success without findings:
    {"status": "ok", "result": {"status": "complete", "findings": []}}
  success with findings:
    {"status": "ok", "result": {"status": "complete", "findings": [{...}]}}
  refused:
    {"status": "refused", "refusal": {"code": "...", "message": "...", "action": "..."}}
  failure:
    {"status": "error", "error": {"code": "...", "message": "...", "action": "..."}}

exit codes:
  0  review completed, no findings
  1  review completed, findings present
  2  refused, such as GitHub not connected or provider out of tokens
  3  failure
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reviewer review",
        description="Run a PR review and print a summary.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pull_request_ref",
        metavar="owner/repo#pr",
        help="the pull request to review, e.g. acme/widgets#42",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "print one JSON document to stdout and nothing else "
            "(no banner, no progress, no colour); human-readable text goes to stderr instead"
        ),
    )
    return parser


def _parse_ref(raw: str) -> tuple[str, str, int]:
    match = _PULL_REQUEST_REF.match(raw)
    if match is None:
        raise ValueError(f"expected owner/repo#pr, got {raw!r}")
    return match["owner"], match["repository"], int(match["number"])


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    args = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    if args and args[0] in {"-h", "--help"}:
        print(parser.format_help(), file=out, end="")
        return 0
    namespace = parser.parse_args(args)

    try:
        owner, repository, pull_request = _parse_ref(namespace.pull_request_ref)
    except ValueError as error:
        payload = JSONCLIResult(status="error", error=agent_surface_error_payload(error))
        _emit(payload, EXIT_ERROR, as_json=namespace.json, out=out, err=err)
        return EXIT_ERROR

    core = AgentSurfaceCore(LiveAgentReviewBackend())
    cli = JSONCLI(core)
    json_argv = [
        "review",
        "--owner",
        owner,
        "--repository",
        repository,
        "--pull-request",
        str(pull_request),
    ]

    try:
        result = cli.run(json_argv)
    except AgentSurfaceRefusal as refusal:
        payload = JSONCLIResult(status="refused", refusal=refusal.as_payload())
        exit_code = EXIT_REFUSED
    except Exception as error:
        payload = JSONCLIResult(status="error", error=agent_surface_error_payload(error))
        exit_code = EXIT_ERROR
    else:
        payload = JSONCLIResult(status="ok", result=result)
        findings = result.get("findings") if isinstance(result, dict) else None
        exit_code = EXIT_OK_FINDINGS if findings else EXIT_OK_NO_FINDINGS

    _emit(payload, exit_code, as_json=namespace.json, out=out, err=err)
    return exit_code


def _emit(
    payload: JSONCLIResult,
    exit_code: int,
    *,
    as_json: bool,
    out: TextIO,
    err: TextIO,
) -> None:
    if as_json:
        write_json_result(out, payload)
        return
    _print_human_summary(payload, out=out, err=err)


def _print_human_summary(payload: JSONCLIResult, *, out: TextIO, err: TextIO) -> None:
    if payload.status == "refused":
        refusal = payload.refusal or {}
        print(f"Review refused: {refusal.get('message', 'unknown reason')}", file=err)
        return
    if payload.status == "error":
        error = payload.error or {}
        message = error.get("message", "unknown error")
        print(f"Review failed: {message}", file=err)
        return
    result = payload.result
    if not isinstance(result, dict):
        print("Review completed.", file=out)
        return
    _print_review_result(result, out=out)


def _print_review_result(result: dict[str, Any], *, out: TextIO) -> None:
    print(
        f"Review {result.get('review_id')} for "
        f"{result.get('owner')}/{result.get('repository')}#{result.get('pull_request')} "
        f"(head {result.get('head_sha')}): status={result.get('status')}",
        file=out,
    )
    findings = result.get("findings") or []
    if not findings:
        print("No findings.", file=out)
        return
    print(f"{len(findings)} finding(s):", file=out)
    for finding in findings:
        label = "verified" if finding.get("verified") else "asserted"
        print(
            f"  [{finding.get('severity')}] {finding.get('title')} "
            f"({finding.get('file_path')}:{finding.get('line_start')}-{finding.get('line_end')}) "
            f"[{label}]",
            file=out,
        )
