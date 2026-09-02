"""`reviewer acp` -- serves the Agent Client Protocol surface over stdio JSON-RPC.

Runner-side (see runner/cli/__init__.py): builds a LiveAgentReviewBackend and speaks JSON-RPC
over stdin/stdout so an ACP client can call actions/list and actions/call without reading this
project's source. Never imports pr_reviewer.db, pr_reviewer.control_plane or pr_reviewer.cli.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import TextIO

from pr_reviewer.agent_surfaces.acp import ACPSurface
from pr_reviewer.agent_surfaces.backend import LiveAgentReviewBackend
from pr_reviewer.agent_surfaces.core import AgentSurfaceCore
from pr_reviewer.runner.cli.agent_surface_io import run_jsonrpc_stdio_loop

_EPILOG = """\
Protocol:
  newline-delimited ACP JSON messages over stdin and stdout
  initialize with method initialize
  list actions with method actions/list
  call actions with method actions/call

Action result shape:
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
        prog="reviewer acp",
        description="Serve the PR Reviewer ACP surface over stdio.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    if args and args[0] in {"-h", "--help"}:
        output = stdout if stdout is not None else None
        print(parser.format_help(), file=output, end="")
        return 0
    parser.parse_args(args)
    surface = ACPSurface(AgentSurfaceCore(LiveAgentReviewBackend()))
    return run_jsonrpc_stdio_loop(surface.handle_message, stdin=stdin, stdout=stdout)
