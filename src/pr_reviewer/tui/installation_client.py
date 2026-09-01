"""Fetch the runner installation snapshot from the hosted control plane."""

from __future__ import annotations

from typing import Protocol

import httpx

from pr_reviewer.tui.installation_snapshot import InstallationSnapshot


class InstallationClient(Protocol):
    def fetch(self, hosted_origin: str, credential: str) -> InstallationSnapshot: ...


class HostedInstallationClient:
    def fetch(self, hosted_origin: str, credential: str) -> InstallationSnapshot:
        origin = hosted_origin.rstrip("/")
        response = httpx.get(
            f"{origin}/api/runner/installation",
            headers={"authorization": f"Bearer {credential}"},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("installation response must be a JSON object")
        return InstallationSnapshot.from_mapping(payload)
