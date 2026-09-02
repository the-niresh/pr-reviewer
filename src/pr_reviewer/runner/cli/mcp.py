"""`reviewer mcp` -- serves the MCP-compatible tool surface over stdio JSON-RPC.

Runner-side (see runner/cli/__init__.py): builds a LiveAgentReviewBackend and speaks JSON-RPC
over stdin/stdout so an MCP client can list tools and run a review without reading this project's
source. Never imports pr_reviewer.db, pr_reviewer.control_plane or pr_reviewer.cli.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TextIO

from pr_reviewer.agent_surfaces.backend import LiveAgentReviewBackend
from pr_reviewer.agent_surfaces.core import AgentSurfaceCore
from pr_reviewer.agent_surfaces.mcp_server import MCPServer
from pr_reviewer.runner.cli.agent_surface_io import run_jsonrpc_stdio_loop


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    del argv
    server = MCPServer(AgentSurfaceCore(LiveAgentReviewBackend()))
    return run_jsonrpc_stdio_loop(server.handle_json_rpc, stdin=stdin, stdout=stdout)
