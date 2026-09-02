"""`reviewer a2a` -- serves the Agent2Agent surface over stdio JSON-RPC.

Runner-side (see runner/cli/__init__.py): builds a LiveAgentReviewBackend and speaks JSON-RPC
over stdin/stdout so an A2A client can send a message/send request without reading this project's
source. Never imports pr_reviewer.db, pr_reviewer.control_plane or pr_reviewer.cli.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TextIO

from pr_reviewer.agent_surfaces.a2a import A2ASurface
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
    surface = A2ASurface(AgentSurfaceCore(LiveAgentReviewBackend()))
    return run_jsonrpc_stdio_loop(surface.handle_json_rpc, stdin=stdin, stdout=stdout)
