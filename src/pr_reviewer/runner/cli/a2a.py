"""`reviewer a2a` -- serves the Agent2Agent surface over stdio JSON-RPC.

Runner-side (see runner/cli/__init__.py): builds a LiveAgentReviewBackend and speaks JSON-RPC
over stdin/stdout so an A2A client can send a message/send request without reading this project's
source. Never imports pr_reviewer.db, pr_reviewer.control_plane or pr_reviewer.cli.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import TextIO

from pr_reviewer.agent_surfaces.a2a import A2ASurface
from pr_reviewer.agent_surfaces.backend import LiveAgentReviewBackend
from pr_reviewer.agent_surfaces.core import AgentSurfaceCore
from pr_reviewer.runner.cli.agent_surface_io import run_jsonrpc_stdio_loop

_EPILOG = """\
Protocol:
  newline-delimited JSON-RPC over stdin and stdout
  get the agent card with method agent/getAuthenticatedExtendedCard
  send work with method message/send

Artifact payload shape:
  status: ok, refused, error
  ok: result contains the review, findings, or prompts
  refused: refusal: {code, message, action}
  error: {code, message, action}

exit codes:
  0  stdio loop ended or help was printed
"""


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    args = list(argv or [])
    parser = argparse.ArgumentParser(
        prog="reviewer a2a",
        description="Serve the PR Reviewer A2A surface over stdio.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    if args and args[0] in {"-h", "--help"}:
        output = stdout if stdout is not None else None
        print(parser.format_help(), file=output, end="")
        return 0
    parser.parse_args(args)
    surface = A2ASurface(AgentSurfaceCore(LiveAgentReviewBackend()))
    return run_jsonrpc_stdio_loop(surface.handle_json_rpc, stdin=stdin, stdout=stdout)
