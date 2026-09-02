"""Shared stdio JSON-RPC loop for the agent surfaces.

`reviewer mcp`, `reviewer a2a` and `reviewer acp` are each one request/response method
(MCPServer.handle_json_rpc, A2ASurface.handle_json_rpc, ACPSurface.handle_message) away from being
a server: read one JSON object per line from stdin, hand it to that method, write one JSON object
per line to stdout. This is that loop, shared so the three subcommands do not grow three slightly
different copies of it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, TextIO

_PARSE_ERROR = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}}
_INVALID_REQUEST = {
    "jsonrpc": "2.0",
    "id": None,
    "error": {"code": -32600, "message": "request must be a JSON object"},
}


def run_jsonrpc_stdio_loop(
    handle: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Read newline-delimited JSON requests from stdin until it closes.

    A line that is not a valid JSON object gets an error reply, not a dead loop: one bad line
    from a client must not kill the whole session.
    """
    input_stream = stdin if stdin is not None else sys.stdin
    output_stream = stdout if stdout is not None else sys.stdout
    for line in input_stream:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            request = json.loads(stripped)
        except ValueError:
            _write(output_stream, _PARSE_ERROR)
            continue
        if not isinstance(request, dict):
            _write(output_stream, _INVALID_REQUEST)
            continue
        _write(output_stream, handle(request))
    return 0


def _write(output_stream: TextIO, payload: dict[str, Any]) -> None:
    print(json.dumps(payload), file=output_stream, flush=True)
