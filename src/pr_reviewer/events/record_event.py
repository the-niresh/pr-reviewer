from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
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
    assert_json_value(value, "$", set())
    return json.dumps(value, separators=(",", ":"))


def assert_json_value(value: object, path: str, ancestors: set[int]) -> None:
    if value is None or isinstance(value, bool | str):
        return

    if isinstance(value, int):
        return

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"Expected a finite JSON number at {path}")
        return

    if isinstance(value, Mapping):
        assert_acyclic(value, path, ancestors)
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"Expected a string key at {path}")
            assert_json_value(item, f"{path}.{key}", ancestors)
        ancestors.remove(id(value))
        return

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        assert_acyclic(value, path, ancestors)
        for index, item in enumerate(value):
            assert_json_value(item, f"{path}[{index}]", ancestors)
        ancestors.remove(id(value))
        return

    raise TypeError(f"Expected a JSON value at {path}")


def assert_acyclic(value: object, path: str, ancestors: set[int]) -> None:
    value_id = id(value)
    if value_id in ancestors:
        raise TypeError(f"Expected an acyclic JSON value at {path}")
    ancestors.add(value_id)
