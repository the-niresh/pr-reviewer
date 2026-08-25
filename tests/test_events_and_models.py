from __future__ import annotations

import math
import uuid

import pytest

from pr_reviewer.db.client import connection
from pr_reviewer.events import list_events_for_job, record_event, serialize_json_object
from pr_reviewer.models import ModelCallInput, record_model_call


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


def test_event_payload_must_be_json_safe() -> None:
    with pytest.raises(TypeError):
        serialize_json_object({"bad": math.inf})

    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(TypeError):
        serialize_json_object(cyclic)  # type: ignore[arg-type]


def test_records_and_lists_events_in_sequence_order() -> None:
    job_id = create_review_job()

    record_event(job_id, "webhook.accepted", {"deliveryId": "a"})
    record_event(job_id, "worker.started", {"deliveryId": "b"})

    events = list_events_for_job(job_id)

    assert [event.event_type for event in events] == ["webhook.accepted", "worker.started"]
    assert events[0].sequence < events[1].sequence


def test_record_model_call_writes_model_row_and_event() -> None:
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
            metadata={"traceId": "trace-1"},
        )
    )

    with connection() as conn:
        model_call = conn.execute(
            """
            select cost_usd::text as cost_usd, latency_ms
            from model_calls
            where review_job_id = %s
            """,
            (job_id,),
        ).fetchone()

    events = list_events_for_job(job_id)

    assert model_call is not None
    assert model_call["cost_usd"] == "0.000000123456"
    assert model_call["latency_ms"] == 42
    assert [event.event_type for event in events] == ["model_call.recorded"]


def test_model_call_rejects_bad_cost_precision() -> None:
    with pytest.raises(TypeError):
        record_model_call(
            ModelCallInput(
                review_job_id=str(uuid.uuid4()),
                provider="openai",
                model="gpt-5-mini",
                prompt_version_id=str(uuid.uuid4()),
                input_tokens=1,
                output_tokens=1,
                cost_usd="0.1234567890123",
                latency_ms=1,
                metadata={},
            )
        )
