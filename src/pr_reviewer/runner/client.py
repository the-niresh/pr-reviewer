"""Outbound HTTPS client for the hosted job protocol (Runtime Task 3).

The runner opens every connection. This module must never import pr_reviewer.control_plane or
pr_reviewer.db: those packages are the hosted plane's handle onto Neon.
"""

from __future__ import annotations

import random
from typing import Any

import httpx

from pr_reviewer.contracts.runner import (
    JobAcknowledgement,
    JobEnvelope,
    JobProtocolDenied,
    LeaseState,
    NoJob,
    RunnerAuthDenied,
)


class RunnerClient:
    POLL_TIMEOUT_SECONDS = 30.0

    def __init__(self, base_url: str, credential: str) -> None:
        self._credential = credential
        self._http = httpx.Client(base_url=base_url, timeout=self.POLL_TIMEOUT_SECONDS)

    @classmethod
    def poll_delay_seconds(cls, attempt: int) -> float:
        jitter = random.uniform(0.25, 1.0)
        return jitter + (0.25 * max(attempt, 1))

    def _auth_headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._credential}"}

    def set_credential(self, credential: str) -> None:
        self._credential = credential

    def claim(self) -> JobEnvelope | NoJob | RunnerAuthDenied:
        response = self._http.post("/api/runner/jobs/claim", headers=self._auth_headers())
        if response.status_code == 401:
            detail = _detail_reason(response)
            if detail == "revoked_runner":
                return RunnerAuthDenied(reason="revoked_runner")
            return RunnerAuthDenied(reason="unknown_credential")
        payload = response.json()
        if payload.get("status") == "no_job" or payload == {}:
            return NoJob()
        return JobEnvelope.model_validate(payload)

    def heartbeat(self, job_id: str, lease_token: str) -> LeaseState:
        response = self._http.post(
            f"/api/runner/jobs/{job_id}/heartbeat",
            headers=self._auth_headers(),
            json={"lease_token": lease_token},
        )
        payload = response.json()
        status = payload.get("status", "invalid_or_expired")
        if status == "active":
            return LeaseState(status="active")
        return LeaseState(status="invalid_or_expired")

    def acknowledge(self, job_id: str, lease_token: str, result: JobAcknowledgement) -> None:
        response = self._http.post(
            f"/api/runner/jobs/{job_id}/ack",
            headers=self._auth_headers(),
            json={"lease_token": lease_token, "result": result.model_dump(mode="json")},
        )
        if response.status_code == 409 or _detail_reason(response) == "invalid_or_expired":
            raise JobProtocolDenied(reason="invalid_or_expired")
        response.raise_for_status()


def _detail_reason(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return ""
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
    return ""
