"""`reviewer acp` -- serves the Agent Client Protocol surface over stdio JSON-RPC.

Runner-side (see runner/cli/__init__.py): builds a LiveAgentReviewBackend and speaks JSON-RPC
over stdin/stdout so an ACP client can call actions/list and actions/call without reading this
project's source. Never imports pr_reviewer.db, pr_reviewer.control_plane or pr_reviewer.cli.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TextIO

from pr_reviewer.agent_surfaces.acp import ACPSurface
from pr_reviewer.agent_surfaces.backend import LiveAgentReviewBackend
from pr_reviewer.agent_surfaces.core import AgentSurfaceCore
from pr_reviewer.runner.cli.agent_surface_io import run_jsonrpc_stdio_loop


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    del argv
    surface = ACPSurface(AgentSurfaceCore(LiveAgentReviewBackend()))
    return run_jsonrpc_stdio_loop(surface.handle_message, stdin=stdin, stdout=stdout)
