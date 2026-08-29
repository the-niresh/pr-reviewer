"""`reviewer trace <job-id>` (Runtime Task 5A).

This is the Phase 6 proof gate: reconstructing one review from its job ID must need no manual
database work. This module is that reconstruction, wired to real storage -- it fetches the hosted
half via control_plane.runner_jobs.fetch_hosted_trace and the local half via
local_store.sqlite.LocalStore.fetch_trace, then hands both to
observability.trace.reconstruct_trace, which does the actual merge and redaction with no I/O of
its own.

This tool needs both a Postgres connection (DATABASE_URL) and a path to the runner's local SQLite
file. The shipped end-user runner never holds both at once -- it only ever has the local file, by
the same design that keeps Neon credentials off the runner entirely (see
docs/superpowers/plans/2026-08-27-hosted-control-plane-local-runner.md's Non-Goals). So this is a
developer/support-side tool run against a copy of, or direct access to, both stores, not a command
the shipped runner binary exposes to an end user.

--json emits a machine-readable export; without it, this prints the redacted human view. Both draw
from the same TraceReconstruction, so they can never disagree about what happened.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import cast

from pr_reviewer.control_plane.runner_jobs import fetch_hosted_trace
from pr_reviewer.db.client import close_pool
from pr_reviewer.local_store.sqlite import LocalStoreCorrupted, open_local_store
from pr_reviewer.observability.trace import (
    LocalTrace,
    RedactionLevel,
    TraceReconstruction,
    TraceSegment,
    reconstruct_trace,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reviewer trace",
        description="Reconstruct one review's trace from hosted agent_events and the runner's "
        "local_events, joined by job id, with no manual database work.",
    )
    parser.add_argument("job_id", help="The review job id (review_jobs.id / local_jobs.job_id)")
    parser.add_argument(
        "--local-store",
        dest="local_store_path",
        required=True,
        help="Path to the runner's local SQLite state file",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Machine-readable JSON export instead of the human view",
    )
    parser.add_argument(
        "--level",
        dest="redaction_level",
        choices=["redacted", "debug"],
        default="redacted",
        help="Redaction level for local-side payload content (default: redacted)",
    )
    return parser


def run(args: Sequence[str]) -> int:
    parsed = build_parser().parse_args(args)

    hosted = fetch_hosted_trace(parsed.job_id)
    local = _fetch_local_trace(parsed.job_id, parsed.local_store_path)

    if hosted is None and local is None:
        print(f"No trace found for job {parsed.job_id} in either store.", file=sys.stderr)
        return 1

    result = reconstruct_trace(
        parsed.job_id,
        hosted,
        local,
        redaction_level=cast(RedactionLevel, parsed.redaction_level),
    )

    if parsed.as_json:
        print(json.dumps(_to_json(result), indent=2))
    else:
        _print_human_view(result)
    return 0


def _fetch_local_trace(job_id: str, local_store_path: str) -> LocalTrace | None:
    try:
        store = open_local_store(local_store_path)
    except LocalStoreCorrupted as exc:
        print(f"warning: local store at {local_store_path} is corrupted: {exc}", file=sys.stderr)
        return None
    try:
        return store.fetch_trace(job_id)
    finally:
        store.close()


def _to_json(result: TraceReconstruction) -> dict[str, object]:
    return {
        "jobId": result.job_id,
        "traceId": result.trace_id,
        "complete": result.is_complete,
        "missingOrigins": sorted(result.missing_origins),
        "segments": [_segment_to_json(segment) for segment in result.segments],
    }


def _segment_to_json(segment: TraceSegment) -> dict[str, object]:
    return {
        "origin": segment.origin,
        "traceId": segment.trace_id,
        "spanId": segment.span_id,
        "parentSpanId": segment.parent_span_id,
        "timestamp": segment.timestamp,
        "kind": segment.kind,
        "payload": dict(segment.payload),
        "placement": segment.placement,
    }


def _print_human_view(result: TraceReconstruction) -> None:
    print(f"Trace for job {result.job_id} (trace {result.trace_id or 'unknown'})")
    if not result.is_complete:
        missing = ", ".join(sorted(result.missing_origins))
        print(f"INCOMPLETE: missing data from: {missing}")
    if not result.segments:
        print("(no events recorded in either store)")
        return
    for segment in result.segments:
        parent = segment.parent_span_id or "-"
        marker = (
            ""
            if segment.placement == "proven"
            else "  [UNORDERED: default position, not derived]"
        )
        print(
            f"[{segment.origin:>6}] {segment.timestamp}  {segment.kind}  "
            f"(span={segment.span_id} parent={parent}){marker}"
        )
        for key, value in segment.payload.items():
            print(f"           {key}: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(sys.argv[1:] if argv is None else argv)
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
