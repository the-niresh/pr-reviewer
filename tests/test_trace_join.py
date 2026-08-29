"""Tests for Runtime Task 5A's pure merge logic: observability.trace.reconstruct_trace.

No database and no SQLite file here on purpose -- these tests fabricate HostedTrace/LocalTrace
directly, so they exercise exactly the merge, ordering, and redaction rules, not any I/O. The
integration path (fetch_hosted_trace, LocalStore.fetch_trace, and the reviewer trace CLI wired to
real storage) is tests/test_trace_cli.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from pr_reviewer.observability.trace import (
    HostedTrace,
    HostedTraceEvent,
    LocalTrace,
    LocalTraceEvent,
    TraceIntegrityError,
    reconstruct_trace,
)

TRACE_ID = "3fae1c2e-0000-0000-0000-000000000001"
OTHER_TRACE_ID = "3fae1c2e-0000-0000-0000-000000000002"


def hosted_event(
    sequence: int, kind: str, payload: dict[str, Any], created_at: datetime
) -> HostedTraceEvent:
    return HostedTraceEvent(sequence=sequence, kind=kind, payload=payload, created_at=created_at)


def local_event(
    sequence: int, kind: str, payload: dict[str, Any], created_at: str
) -> LocalTraceEvent:
    return LocalTraceEvent(sequence=sequence, kind=kind, payload=payload, created_at=created_at)


def test_hosted_only_trace_is_reported_incomplete_and_names_local_as_missing() -> None:
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(hosted_event(1, "model_call.recorded", {}, datetime(2026, 8, 30, tzinfo=UTC)),),
    )

    result = reconstruct_trace("job-1", hosted, None)

    assert result.is_complete is False
    assert result.missing_origins == frozenset({"local"})
    assert len(result.segments) == 1
    assert result.segments[0].origin == "hosted"


def test_local_only_trace_is_reported_incomplete_and_names_hosted_as_missing() -> None:
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(local_event(1, "job_claimed", {}, "2026-08-30T00:00:00.000Z"),),
    )

    result = reconstruct_trace("job-1", None, local)

    assert result.is_complete is False
    assert result.missing_origins == frozenset({"hosted"})
    assert len(result.segments) == 1
    assert result.segments[0].origin == "local"


def test_neither_store_present_reports_both_origins_missing_with_no_segments() -> None:
    result = reconstruct_trace("job-1", None, None)

    assert result.is_complete is False
    assert result.missing_origins == frozenset({"hosted", "local"})
    assert result.segments == ()


def test_both_stores_present_is_reported_complete() -> None:
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(hosted_event(1, "model_call.recorded", {}, datetime(2026, 8, 30, tzinfo=UTC)),),
    )
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(local_event(1, "job_claimed", {}, "2026-08-30T00:00:00.000Z"),),
    )

    result = reconstruct_trace("job-1", hosted, local)

    assert result.is_complete is True
    assert result.missing_origins == frozenset()


def test_within_store_ordering_uses_recorded_sequence_not_input_order_and_chains_parent_spans() -> (
    None
):
    # Events supplied out of sequence order on purpose: only the recorded sequence, never
    # insertion order, may decide the chain.
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(
            hosted_event(5, "model_call.recorded", {}, datetime(2026, 8, 30, 1, tzinfo=UTC)),
            hosted_event(2, "model_call.recorded", {}, datetime(2026, 8, 30, 0, tzinfo=UTC)),
        ),
    )

    result = reconstruct_trace("job-1", hosted, None)

    assert [segment.span_id for segment in result.segments] == ["hosted:2", "hosted:5"]
    assert result.segments[0].parent_span_id is None
    assert result.segments[1].parent_span_id == "hosted:2"


def test_hosted_acknowledged_event_is_placed_after_local_chain_despite_earlier_timestamp() -> None:
    # This is the "offline runner acknowledged late" shape and the proof that ordering never
    # uses wall-clock time: the hosted ack row is stamped earlier than the local events (a clock
    # could easily do this -- the runner reconnecting after being offline for hours is one way,
    # simple clock skew is another), yet it must still land after the local chain it depends on,
    # because that placement comes from the runner ack protocol, never from comparing timestamps.
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(
            hosted_event(
                1, "review_job_acknowledged", {}, datetime(2020, 1, 1, tzinfo=UTC)
            ),
        ),
    )
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(
            local_event(1, "job_claimed", {}, "2026-08-30T12:00:00.000Z"),
            local_event(2, "snapshot_fetched", {}, "2026-08-30T12:05:00.000Z"),
        ),
    )

    result = reconstruct_trace("job-1", hosted, local)

    kinds = [segment.kind for segment in result.segments]
    assert kinds == ["job_claimed", "snapshot_fetched", "review_job_acknowledged"]
    ack_segment = result.segments[-1]
    assert ack_segment.parent_span_id == "local:2"


def test_hosted_event_kinds_other_than_acknowledged_default_to_before_the_local_chain() -> None:
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(hosted_event(1, "model_call.recorded", {}, datetime(2026, 8, 30, tzinfo=UTC)),),
    )
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(local_event(1, "job_claimed", {}, "2026-08-30T12:00:00.000Z"),),
    )

    result = reconstruct_trace("job-1", hosted, local)

    kinds = [segment.kind for segment in result.segments]
    assert kinds == ["model_call.recorded", "job_claimed"]


def test_review_job_failed_segment_is_marked_unordered_not_proven() -> None:
    # review_job_failed is written by worker/main.py, which is not provably tied to the runner
    # ack protocol the way review_job_acknowledged is -- its before-the-local-chain position is
    # this module's default, not something it derived, and placement must say so.
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(hosted_event(1, "review_job_failed", {}, datetime(2026, 8, 30, tzinfo=UTC)),),
    )
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(local_event(1, "job_claimed", {}, "2026-08-30T12:00:00.000Z"),),
    )

    result = reconstruct_trace("job-1", hosted, local)

    failed_segment = next(s for s in result.segments if s.kind == "review_job_failed")
    assert failed_segment.placement == "unordered"


def test_review_job_acknowledged_segment_is_marked_proven() -> None:
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(hosted_event(1, "review_job_acknowledged", {}, datetime(2026, 8, 30, tzinfo=UTC)),),
    )
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(local_event(1, "job_claimed", {}, "2026-08-30T12:00:00.000Z"),),
    )

    result = reconstruct_trace("job-1", hosted, local)

    ack_segment = next(s for s in result.segments if s.kind == "review_job_acknowledged")
    assert ack_segment.placement == "proven"


def test_local_segments_are_always_marked_proven() -> None:
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(
            local_event(1, "job_claimed", {}, "2026-08-30T12:00:00.000Z"),
            local_event(2, "snapshot_fetched", {}, "2026-08-30T12:05:00.000Z"),
        ),
    )

    result = reconstruct_trace("job-1", None, local)

    assert all(segment.placement == "proven" for segment in result.segments)


def test_mismatched_trace_ids_between_hosted_and_local_raises_trace_integrity_error() -> None:
    hosted = HostedTrace(trace_id=TRACE_ID, events=())
    local = LocalTrace(trace_id=OTHER_TRACE_ID, events=())

    with pytest.raises(TraceIntegrityError):
        reconstruct_trace("job-1", hosted, local)


def test_redaction_strips_secret_like_keys_regardless_of_configured_level() -> None:
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(
            local_event(
                1,
                "github_call",
                {"githubToken": "ghs_supersecrettoken", "modelKey": "sk-abcdefg"},
                "2026-08-30T00:00:00.000Z",
            ),
        ),
    )

    redacted_result = reconstruct_trace("job-1", None, local, redaction_level="redacted")
    debug_result = reconstruct_trace("job-1", None, local, redaction_level="debug")

    for result in (redacted_result, debug_result):
        payload = result.segments[0].payload
        assert "ghs_supersecrettoken" not in str(payload)
        assert "sk-abcdefg" not in str(payload)


def test_redaction_strips_sensitive_content_at_redacted_level_but_not_at_debug_level() -> None:
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(
            local_event(
                1,
                "finding_decided",
                {"rationale": "widget.value can be None on line 11", "confidence": 0.8},
                "2026-08-30T00:00:00.000Z",
            ),
        ),
    )

    redacted_result = reconstruct_trace("job-1", None, local, redaction_level="redacted")
    debug_result = reconstruct_trace("job-1", None, local, redaction_level="debug")

    redacted_payload = redacted_result.segments[0].payload
    debug_payload = debug_result.segments[0].payload
    assert "widget.value" not in str(redacted_payload)
    assert redacted_payload["confidence"] == 0.8
    assert debug_payload["rationale"] == "widget.value can be None on line 11"


def test_redaction_walks_nested_local_payloads_not_just_top_level_keys() -> None:
    local = LocalTrace(
        trace_id=TRACE_ID,
        events=(
            local_event(
                1,
                "finding_decided",
                {"finding": {"rationale": "leaked rationale text", "id": "finding-1"}},
                "2026-08-30T00:00:00.000Z",
            ),
        ),
    )

    result = reconstruct_trace("job-1", None, local, redaction_level="redacted")

    payload = result.segments[0].payload
    assert "leaked rationale text" not in str(payload)
    assert payload["finding"]["id"] == "finding-1"


def test_hosted_payload_is_carried_through_untouched_when_it_has_no_sensitive_looking_keys() -> (
    None
):
    hosted = HostedTrace(
        trace_id=TRACE_ID,
        events=(
            hosted_event(
                1,
                "model_call.recorded",
                {"provider": "openai", "inputTokens": 10, "costUsd": "0.000001"},
                datetime(2026, 8, 30, tzinfo=UTC),
            ),
        ),
    )

    result = reconstruct_trace("job-1", hosted, None)

    assert result.segments[0].payload == {
        "provider": "openai",
        "inputTokens": 10,
        "costUsd": "0.000001",
    }
