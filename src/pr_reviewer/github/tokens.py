from __future__ import annotations

import time
from dataclasses import dataclass

import jwt


@dataclass(frozen=True)
class GitHubAppSettings:
    app_id: str
    private_key: str


def build_app_jwt(settings: GitHubAppSettings, now_seconds: int | None = None) -> str:
    now = int(time.time()) if now_seconds is None else now_seconds
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": settings.app_id,
    }
    encoded = jwt.encode(payload, settings.private_key, algorithm="RS256")
    if not isinstance(encoded, str):
        raise TypeError("GitHub app JWT encoder returned bytes")
    return encoded
