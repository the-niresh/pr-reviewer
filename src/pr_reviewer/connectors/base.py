"""In-process connector return value. Never persisted. Never an audit input.

T is unbounded on purpose. InstallationToken and PullRequestSnapshot both carry
secrets, so a TypeVar bound would not stop a leak. record_connector_run rejects
this type. Only ConnectorAudit is written to connector_runs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConnectorName = Literal["github"]
ConnectorOperation = Literal["create_installation_token", "fetch_pull_request"]
ConnectorOutcome = Literal["success", "error"]
ConnectorErrorKind = Literal["timeout", "http_error"]


class ConnectorResult[T](BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: ConnectorName
    operation: ConnectorOperation
    outcome: ConnectorOutcome
    value: T | None = None
    error_kind: ConnectorErrorKind | None = None
    status_code: int | None = None
    latency_ms: int = Field(ge=0)
    request_bytes: int = Field(ge=0)
    response_bytes: int = Field(ge=0)
