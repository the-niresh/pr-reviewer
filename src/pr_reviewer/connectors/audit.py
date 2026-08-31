"""Allowlisted connector audit: typed fields first, redaction second.

ConnectorAudit is the only persistable shape. record_connector_run rejects
any other object. This module never imports the in-process result type
and never reads its payload.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pr_reviewer.db.client import Row

# Shape, not an enumerated name list: any gh<letter>_ token plus github_pat_.
# Bound is low on purpose so a short canary such as gho_leaked still matches.
_TOKEN_RE = re.compile(r"(?:gh[a-z]_|github_pat_)[A-Za-z0-9_]{4,}", re.IGNORECASE)
# Validator: fire on a bare header even when there is no END line.
_PEM_HEADER_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)
# Redaction: remove the material, so this must span the full BEGIN ... END block.
_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_X_ACCESS_RE = re.compile(r"x-access-token:[^@\s]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(?:authorization\s*[:=]\s*)?bearer\s+\S+", re.IGNORECASE)


def _reject_secret_text(value: str) -> str:
    if _TOKEN_RE.search(value):
        raise ValueError("typed audit field cannot hold a credential")
    if _PEM_HEADER_RE.search(value):
        raise ValueError("typed audit field cannot hold a private key")
    return value


class ConnectorAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: uuid.UUID
    connector: Literal["github"]
    operation: Literal[
        "create_installation_token", "fetch_pull_request", "create_pull_request_review"
    ]
    external_id: str | None = None
    request_bytes: int = Field(ge=0)
    response_bytes: int = Field(ge=0)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("connector", "operation", "external_id", "payload_hash")
    @classmethod
    def _typed_fields_reject_secrets(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _reject_secret_text(value)


def _redact_string(text: str) -> str:
    redacted = _PEM_BLOCK_RE.sub("[redacted-key]", text)
    leftover = _PEM_HEADER_RE.search(redacted)
    if leftover is not None:
        # Truncated paste: no END, so the block pattern missed. Drop the header
        # and leftover body so key material cannot survive a .sub() miss.
        redacted = redacted[: leftover.start()] + "[redacted-key]"
    redacted = _X_ACCESS_RE.sub("[redacted-git-url]", redacted)
    redacted = _BEARER_RE.sub("[redacted-auth]", redacted)
    redacted = _TOKEN_RE.sub("[redacted-token]", redacted)
    return redacted.replace("stolen_auth", "[redacted]")


def redact_audit_value(value: object) -> object:
    """Second defense: strip credentials and source markers from free text."""
    if isinstance(value, dict):
        return {
            str(redact_audit_value(key)): redact_audit_value(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_audit_value(nested) for nested in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def record_connector_run(
    db: Connection[Row],
    audit: ConnectorAudit,
    review_job_id: str | None,
) -> str:
    if not isinstance(audit, ConnectorAudit):
        raise TypeError(
            "in-process connector return values cannot be recorded; pass a ConnectorAudit"
        )
    external_id = audit.external_id
    if isinstance(external_id, str):
        redacted = redact_audit_value(external_id)
        external_id = redacted if isinstance(redacted, str) else None
    cursor = db.execute(
        """
        insert into connector_runs (
          review_job_id,
          trace_id,
          connector,
          operation,
          external_id,
          request_bytes,
          response_bytes,
          payload_hash
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            review_job_id,
            audit.trace_id,
            audit.connector,
            audit.operation,
            external_id,
            audit.request_bytes,
            audit.response_bytes,
            audit.payload_hash,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("connector_runs insert did not return an id")
    return str(row["id"])
