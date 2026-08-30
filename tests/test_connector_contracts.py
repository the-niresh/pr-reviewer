"""Failing tests for connector contracts and allowlisted audit logs (master Task 8).

Typed fields first, recursive redaction second. An audit row that can hold a header
dictionary will eventually hold one. These canaries decode and inspect the constructed
object and the persisted row, the same way the live-sign-in cookie test decodes the
cookie instead of trusting the type name.

Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from pr_reviewer.db.client import connection
from pr_reviewer.jobs import enqueue_review_job

_GITHUB_TOKEN_PREFIXES = ("gho_", "ghu_", "ghs_", "github_pat_")
_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----"
_SOURCE_SNIPPET = "def stolen_auth():\n    return secret"
_CREDENTIAL_URL = "https://x-access-token:gho_leaked@github.com/acme/widgets.git"
_TRACE_MODULE = (
    Path(__file__).resolve().parent.parent / "src" / "pr_reviewer" / "observability" / "trace.py"
)


def _job_with_trace() -> tuple[str, str]:
    with connection() as conn, conn.transaction():
        conn.execute(
            "insert into installations (id, account_login) values (%s, %s)",
            (8301, "acme"),
        )
    payload = {
        "action": "opened",
        "installation": {"id": 8301},
        "repository": {"id": 93001, "name": "widgets"},
        "pull_request": {
            "number": 4,
            "base": {"sha": "a" * 40},
            "head": {"sha": "b" * 40},
        },
    }
    assert enqueue_review_job("delivery-connector-1", "pull_request", payload) == "enqueued"
    with connection() as conn:
        row = conn.execute(
            "select id, trace_id from review_jobs where delivery_id = %s",
            ("delivery-connector-1",),
        ).fetchone()
    assert row is not None
    assert row["trace_id"] is not None
    return str(row["id"]), str(row["trace_id"])


def _audit(*, trace_id: str, **overrides: object) -> object:
    from pr_reviewer.connectors.audit import ConnectorAudit

    fields: dict[str, object] = {
        "trace_id": uuid.UUID(trace_id),
        "connector": "github",
        "operation": "fetch_pull_request",
        "external_id": "req-1",
        "request_bytes": 32,
        "response_bytes": 64,
        "payload_hash": "a" * 64,
    }
    fields.update(overrides)
    return ConnectorAudit(**fields)


def _walk_for_secrets(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _walk_for_secrets(key)
            _walk_for_secrets(nested)
        return
    if isinstance(value, list | tuple):
        for nested in value:
            _walk_for_secrets(nested)
        return
    text = str(value)
    lowered = text.lower()
    for prefix in _GITHUB_TOKEN_PREFIXES:
        assert prefix not in lowered, f"audit carried GitHub token pattern {prefix}"
    assert _PRIVATE_KEY.lower() not in lowered
    assert "stolen_auth" not in text
    assert "x-access-token:" not in lowered
    assert "authorization" not in lowered or "bearer" not in lowered


def test_connector_audit_rejects_raw_headers() -> None:
    from pr_reviewer.connectors.audit import ConnectorAudit

    with pytest.raises(ValidationError):
        ConnectorAudit(
            trace_id=uuid.uuid4(),
            connector="github",
            operation="fetch_pull_request",
            external_id="req-1",
            request_bytes=1,
            response_bytes=1,
            payload_hash="a" * 64,
            headers={"Authorization": "Bearer gho_must_never_be_stored"},
        )


def test_connector_audit_rejects_a_request_or_response_dictionary() -> None:
    from pr_reviewer.connectors.audit import ConnectorAudit

    base = {
        "trace_id": uuid.uuid4(),
        "connector": "github",
        "operation": "fetch_pull_request",
        "external_id": "req-1",
        "request_bytes": 1,
        "response_bytes": 1,
        "payload_hash": "a" * 64,
    }
    with pytest.raises(ValidationError):
        ConnectorAudit(**base, request={"url": _CREDENTIAL_URL})
    with pytest.raises(ValidationError):
        ConnectorAudit(**base, response={"body": _SOURCE_SNIPPET})


def test_connector_audit_rejects_body_payload_token_and_private_key_fields() -> None:
    from pr_reviewer.connectors.audit import ConnectorAudit

    base = {
        "trace_id": uuid.uuid4(),
        "connector": "github",
        "operation": "fetch_pull_request",
        "external_id": "req-1",
        "request_bytes": 1,
        "response_bytes": 1,
        "payload_hash": "a" * 64,
    }
    for extra in (
        {"body": _SOURCE_SNIPPET},
        {"payload": {"patch": "@@ stolen"}},
        {"token": "gho_must_never_be_stored"},
        {"private_key": _PRIVATE_KEY},
        {"authorization": "Bearer gho_must_never_be_stored"},
    ):
        with pytest.raises(ValidationError):
            ConnectorAudit(**base, **extra)


def test_connector_audit_rejects_a_token_stuffed_into_a_typed_string_field() -> None:
    with pytest.raises(ValidationError):
        _audit(trace_id=str(uuid.uuid4()), operation="gho_must_never_be_an_operation")
    with pytest.raises(ValidationError):
        _audit(trace_id=str(uuid.uuid4()), external_id="gho_must_never_be_an_id")
    with pytest.raises(ValidationError):
        _audit(trace_id=str(uuid.uuid4()), payload_hash=_SOURCE_SNIPPET)


def test_connector_audit_dump_contains_hash_and_bytes_never_a_body() -> None:
    audit = _audit(trace_id=str(uuid.uuid4()))
    dumped = audit.model_dump(mode="json")
    assert "payload_hash" in dumped
    assert "request_bytes" in dumped
    assert "response_bytes" in dumped
    assert "body" not in dumped
    assert "payload" not in dumped
    assert "headers" not in dumped
    _walk_for_secrets(dumped)
    blob = json.dumps(dumped)
    _walk_for_secrets(blob)


def test_redaction_is_a_second_defense_and_strips_secrets_from_free_text() -> None:
    from pr_reviewer.connectors.audit import redact_audit_value

    redacted = redact_audit_value(
        {
            "Authorization": "Bearer gho_leaked",
            "url": _CREDENTIAL_URL,
            "key": _PRIVATE_KEY,
            "source": _SOURCE_SNIPPET,
        }
    )
    _walk_for_secrets(redacted)
    assert "gho_leaked" not in str(redact_audit_value("Bearer gho_leaked"))


def test_record_connector_run_stores_the_job_trace_id_and_no_body() -> None:
    from pr_reviewer.connectors.audit import record_connector_run

    job_id, trace_id = _job_with_trace()
    audit = _audit(trace_id=trace_id)
    with connection() as conn:
        run_id = record_connector_run(conn, audit, job_id)
        assert run_id
        row = conn.execute(
            "select * from connector_runs where id = %s",
            (run_id,),
        ).fetchone()
    assert row is not None
    dumped = dict(row)
    assert str(dumped["trace_id"]) == trace_id
    assert dumped["payload_hash"] == "a" * 64
    assert dumped["request_bytes"] == 32
    assert dumped["response_bytes"] == 64
    for name in dumped:
        assert name not in {
            "body",
            "payload",
            "headers",
            "request",
            "response",
            "token",
            "authorization",
        }
    _walk_for_secrets(dumped)


def test_connector_runs_schema_has_trace_id_and_cannot_hold_a_body() -> None:
    with connection() as conn:
        rows = conn.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public' and table_name = 'connector_runs'
            """
        ).fetchall()
    names = {str(row["column_name"]) for row in rows}
    assert "trace_id" in names
    assert "payload_hash" in names
    for forbidden in (
        "body",
        "payload",
        "headers",
        "request",
        "response",
        "token",
        "authorization",
    ):
        assert forbidden not in names


def test_trace_module_does_not_claim_connector_runs_is_missing() -> None:
    """Task 5A deferred the third join. Once this table exists the old comment is false.

    reconstruct_trace stays two-source for now. The follow-up is named Task 8A at this file.
    """
    text = _TRACE_MODULE.read_text(encoding="utf-8")
    assert "Task 8 is unstarted" not in text
    assert "there is no connector_runs table" not in text
    assert "Task 8A" in text
    assert "connector_runs" in text


def test_connectors_package_is_hosted_and_must_not_import_runner_side() -> None:
    """connectors/ wraps hosted GitHub App calls and writes connector_runs to Neon."""
    from test_package_boundaries import (
        EXPECTED_EXISTING_PACKAGES,
        GUARDED_PACKAGES,
        HOSTED_SIDE_FORBIDDEN_TARGETS,
        HOSTED_SIDE_PACKAGES,
        SRC_ROOT,
        _imports_targeting,
        collect_imports,
    )

    assert "connectors" in GUARDED_PACKAGES
    assert "connectors" in EXPECTED_EXISTING_PACKAGES
    assert "connectors" in HOSTED_SIDE_PACKAGES
    package_dir = SRC_ROOT / "connectors"
    assert package_dir.is_dir()
    imports = collect_imports(package_dir)
    for forbidden in HOSTED_SIDE_FORBIDDEN_TARGETS:
        hits = _imports_targeting(imports, forbidden)
        assert not hits, f"connectors/* must not import {forbidden}/*, found: {sorted(hits)}"
