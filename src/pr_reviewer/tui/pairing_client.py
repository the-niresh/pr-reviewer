"""Hosted pairing HTTP client for the TUI connect screen."""

from __future__ import annotations

from typing import Literal, Protocol

import httpx

PairingStatus = Literal["pending", "exchangeable", "invalid_or_expired"]


class PairingClient(Protocol):
    def create_code(self, device_name: str, challenge: str) -> str: ...

    def status(self, code: str, challenge: str) -> PairingStatus: ...

    def exchange(self, code: str, proof: str) -> str: ...


class HostedPairingClient:
    def __init__(self, hosted_origin: str) -> None:
        self._hosted_origin = hosted_origin.rstrip("/")

    def create_code(self, device_name: str, challenge: str) -> str:
        response = httpx.post(
            f"{self._hosted_origin}/api/runner/pairing-codes",
            json={"device_name": device_name, "challenge": challenge},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        code = payload.get("code")
        if not isinstance(code, str) or not code:
            raise RuntimeError("pairing create response missing code")
        return code

    def status(self, code: str, challenge: str) -> PairingStatus:
        response = httpx.get(
            f"{self._hosted_origin}/api/runner/pairing-codes/status",
            params={"code": code, "challenge": challenge},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        raw_state = payload.get("state")
        if raw_state == "pending":
            return "pending"
        if raw_state == "exchangeable":
            return "exchangeable"
        return "invalid_or_expired"

    def exchange(self, code: str, proof: str) -> str:
        response = httpx.post(
            f"{self._hosted_origin}/api/runner/pairing-codes/exchange",
            json={"code": code, "proof": proof},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        credential = payload.get("credential")
        if not isinstance(credential, str) or not credential:
            raise RuntimeError("pairing exchange response missing credential")
        return credential
