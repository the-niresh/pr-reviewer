from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pr_reviewer.db.client import connection
from pr_reviewer.events.record_event import JsonObject, serialize_json_object

ModelProvider = Literal["openai", "anthropic"]
COST_USD_PATTERN = re.compile(r"^(?:0|[1-9]\d{0,5})(?:\.\d{1,12})?$")


@dataclass(frozen=True)
class ModelCallInput:
    review_job_id: str
    provider: ModelProvider
    model: str
    prompt_version_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: str
    latency_ms: int
    metadata: JsonObject


def record_model_call(input_value: ModelCallInput) -> None:
    validate_model_call_input(input_value)
    with connection() as conn, conn.transaction():
        cursor = conn.execute(
            """
            insert into model_calls (
              review_job_id,
              prompt_version_id,
              provider,
              model_name,
              input_tokens,
              output_tokens,
              cost_usd,
              latency_ms,
              request_metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s::numeric, %s, %s::jsonb)
            returning id
            """,
            (
                input_value.review_job_id,
                input_value.prompt_version_id,
                input_value.provider,
                input_value.model,
                input_value.input_tokens,
                input_value.output_tokens,
                input_value.cost_usd,
                input_value.latency_ms,
                serialize_json_object(input_value.metadata),
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Model call insert did not return an id")

        model_call_id = str(row["id"])
        conn.execute(
            """
            insert into agent_events (review_job_id, event_type, payload)
            values (%s, %s, %s::jsonb)
            """,
            (
                input_value.review_job_id,
                "model_call.recorded",
                serialize_json_object(
                    {
                        "modelCallId": model_call_id,
                        "provider": input_value.provider,
                        "model": input_value.model,
                        "promptVersionId": input_value.prompt_version_id,
                        "inputTokens": input_value.input_tokens,
                        "outputTokens": input_value.output_tokens,
                        "costUsd": input_value.cost_usd,
                        "latencyMs": input_value.latency_ms,
                    }
                ),
            ),
        )


def validate_model_call_input(input_value: ModelCallInput) -> None:
    if input_value.input_tokens < 0:
        raise TypeError("input_tokens must be a non-negative integer")
    if input_value.output_tokens < 0:
        raise TypeError("output_tokens must be a non-negative integer")
    if input_value.latency_ms < 0:
        raise TypeError("latency_ms must be a non-negative integer")
    if COST_USD_PATTERN.fullmatch(input_value.cost_usd) is None:
        raise TypeError("cost_usd must be a non-negative decimal string with at most 12 decimals")
