"""Hosted lifecycle events (Runtime Task 1B).

A hosted event row is a redacted lifecycle event: identifiers, enums, and aggregate numbers,
never a nested structure. serialize_json_object enforces that here, at the application layer, by
rejecting any payload value that is itself an object or array -- not a validated string, a flat
shape with no depth for a findings list, a diff, or a sandbox log to hide in. migration
202608291930_rescope_hosted_events.sql's agent_events_payload_is_flat CHECK constraint enforces
the identical rule at the database layer, so a writer that reaches the table through raw SQL
rather than this function is still stopped.

JsonObject/JsonValue stay fully recursive: they describe whatever a jsonb column can hold in
general (this file's read path, and other jsonb columns elsewhere), not the narrower flat shape
this file's write path now enforces.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from pr_reviewer.db.client import connection

type JsonPrimitive = bool | int | float | str | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True)
class AgentEvent:
    id: str
    sequence: int
    review_job_id: str | None
    event_type: str
    payload: JsonObject
    created_at: datetime


def record_event(review_job_id: str, event_type: str, payload: JsonObject) -> None:
    with connection() as conn:
        conn.execute(
            """
            insert into agent_events (review_job_id, event_type, payload)
            values (%s, %s, %s::jsonb)
            """,
            (review_job_id, event_type, serialize_json_object(payload)),
        )


def serialize_json_object(value: JsonObject) -> str:
    assert_flat_json_object(value)
    return json.dumps(value, separators=(",", ":"))


def assert_flat_json_object(value: JsonObject) -> None:
    """The top-level object's values must be JSON scalars: no nested object, no nested array.
    A cyclic structure is necessarily a nested object (a dict cannot contain itself as a scalar),
    so rejecting nesting outright also rejects a cycle, with no need to track visited ids.
    """
    if not isinstance(value, Mapping):
        raise TypeError("Expected a JSON object for a hosted event payload")
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"Expected a string key, got {key!r}")
        assert_json_scalar(item, key)


def assert_json_scalar(value: object, key: str) -> None:
    if value is None or isinstance(value, bool | str):
        return

    if isinstance(value, int):
        return

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"Expected a finite JSON number at {key!r}")
        return

    raise TypeError(
        f"Expected a flat JSON scalar (bool, int, float, str, or None) at {key!r}; a hosted "
        "event payload cannot carry a nested object or array"
    )
