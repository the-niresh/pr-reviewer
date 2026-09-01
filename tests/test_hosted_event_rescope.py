"""Tests for Runtime Task 1B: re-scoping hosted events and emptying HOSTED_EXEMPTIONS.

agent_events and model_calls were the last two hosted tables with a documented, unenforced
exemption (control_plane/boundary.py's HOSTED_EXEMPTIONS): both had live writers and no local
store to move detail to until Task 5 existed. This is a re-scope, not a deletion -- the boundary
still permits redacted lifecycle events and aggregate token/cost numbers on the hosted plane, it
forbids a free-form payload and per-call model detail.

Two enforcement layers are tested here on purpose, not one: record_event.serialize_json_object
rejects a nested payload value in Python, and agent_events_payload_is_flat (the migration's CHECK
constraint) rejects one in the database, so a writer that reaches the table by any path other than
serialize_json_object is still stopped. Task 1A's retired-table tests use the same two-layer
pattern for the same reason: convention is not a boundary.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from pr_reviewer.contracts.errors import ReviewJobErrorClass
from pr_reviewer.db.client import connection
from pr_reviewer.events.record_event import record_event
from pr_reviewer.events.record_model_call import ModelCallInput, record_model_call
from pr_reviewer.jobs.fail_review_job import fail_review_job

FORBIDDEN_MODEL_CALLS_COLUMNS = frozenset(
    {"request_metadata", "response_metadata", "prompt", "output", "output_hash"}
)


def create_review_job() -> str:
    with connection() as conn:
        delivery_id = f"delivery-{uuid.uuid4()}"
        conn.execute(
            "insert into github_deliveries (id, event_name) values (%s, 'pull_request')",
            (delivery_id,),
        )
        row = conn.execute(
            "insert into review_jobs (delivery_id, status) values (%s, 'pending') returning id",
            (delivery_id,),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def create_prompt_version() -> str:
    with connection() as conn:
        row = conn.execute(
            """
            insert into prompt_versions (name, version, content)
            values ('reviewer', %s, 'content')
            returning id
            """,
            (str(uuid.uuid4()),),
        ).fetchone()
    assert row is not None
    return str(row["id"])


def test_record_event_rejects_a_nested_object_value() -> None:
    job_id = create_review_job()

    with pytest.raises(TypeError):
        record_event(job_id, "job.detail_leaked", {"finding": {"title": "leaked"}})


def test_record_event_rejects_a_nested_array_value() -> None:
    job_id = create_review_job()

    with pytest.raises(TypeError):
        record_event(job_id, "job.detail_leaked", {"evidence": ["line 1 leaked"]})


def test_record_event_still_accepts_a_flat_payload_of_scalars() -> None:
    job_id = create_review_job()

    record_event(
        job_id,
        "webhook.accepted",
        {"deliveryId": "a", "attempt": 1, "cached": False, "note": None},
    )

    with connection() as conn:
        row = conn.execute(
            "select payload from agent_events where review_job_id = %s", (job_id,)
        ).fetchone()
    assert row is not None
    assert row["payload"] == {"deliveryId": "a", "attempt": 1, "cached": False, "note": None}


def test_inserting_a_nested_payload_directly_is_rejected_by_the_database() -> None:
    # Proves the boundary survives a writer that bypasses serialize_json_object entirely --
    # the same reasoning as test_inserting_into_a_retired_table_is_rejected_by_the_database.
    job_id = create_review_job()

    with (
        pytest.raises(psycopg.errors.CheckViolation),
        connection() as conn,
        conn.transaction(),
    ):
        conn.execute(
            """
            insert into agent_events (review_job_id, event_type, payload)
            values (%s, %s, %s::jsonb)
            """,
            (job_id, "job.detail_leaked", '{"finding": {"title": "leaked"}}'),
        )


def test_model_calls_has_no_columns_for_prompt_output_or_free_form_metadata() -> None:
    with connection() as conn:
        rows = conn.execute(
            """
            select column_name from information_schema.columns
            where table_schema = 'public' and table_name = 'model_calls'
            """
        ).fetchall()

    columns = {str(row["column_name"]) for row in rows}
    present = columns & FORBIDDEN_MODEL_CALLS_COLUMNS
    assert not present, f"model_calls must never hold these columns again: {present}"


def test_model_call_input_has_no_metadata_field_left_to_widen() -> None:
    with pytest.raises(TypeError):
        ModelCallInput(  # type: ignore[call-arg]
            review_job_id=str(uuid.uuid4()),
            provider="openai",
            model="gpt-5-mini",
            prompt_version_id=str(uuid.uuid4()),
            input_tokens=1,
            output_tokens=1,
            cost_usd="0.000000",
            latency_ms=1,
            metadata={"prompt": "leaked prompt text"},
        )


def test_record_model_call_writes_aggregates_only() -> None:
    job_id = create_review_job()
    prompt_version_id = create_prompt_version()

    record_model_call(
        ModelCallInput(
            review_job_id=job_id,
            provider="openai",
            model="gpt-5-mini",
            prompt_version_id=prompt_version_id,
            input_tokens=10,
            output_tokens=5,
            cost_usd="0.000000123456",
            latency_ms=42,
        )
    )

    with connection() as conn:
        row = conn.execute(
            "select * from model_calls where review_job_id = %s", (job_id,)
        ).fetchone()

    assert row is not None
    assert set(row.keys()) & FORBIDDEN_MODEL_CALLS_COLUMNS == set()


def test_fail_review_job_rejects_a_raw_string_error() -> None:
    job_id = create_review_job()

    with pytest.raises(TypeError):
        fail_review_job(job_id, "worker-1", "a raw stack trace string")  # type: ignore[arg-type]


def test_fail_review_job_writes_the_closed_set_value_not_prose() -> None:
    job_id = create_review_job()
    with connection() as conn:
        conn.execute(
            "update review_jobs set status = 'running', locked_by = %s where id = %s",
            ("worker-1", job_id),
        )

    fail_review_job(job_id, "worker-1", ReviewJobErrorClass.WORKER_CRASHED)

    with connection() as conn:
        row = conn.execute(
            "select last_error from review_jobs where id = %s", (job_id,)
        ).fetchone()

    assert row is not None
    assert row["last_error"] == "worker_crashed"


def test_hosted_exemptions_is_empty_and_the_schema_still_passes() -> None:
    from pr_reviewer.control_plane.boundary import HOSTED_EXEMPTIONS, assert_no_private_columns

    assert frozenset() == HOSTED_EXEMPTIONS
    with connection() as conn:
        assert_no_private_columns(conn)
