"""Operator-declared notification channels. Webhook URLs are never stored."""

from __future__ import annotations

import re
import uuid

from pr_reviewer.db.client import connection

_ENDPOINT_HASH = re.compile(r"^[0-9a-f]{64}$")
_TRANSPORTS = frozenset({"slack", "telegram", "discord"})
_PURPOSES = frozenset({"security_alert", "review_ping"})
_CONFIDENTIALITY = frozenset({"restricted", "ordinary"})


def declare_notification_channel(
    *,
    installation_id: int,
    name: str,
    transport: str,
    purpose: str,
    endpoint_hash: str,
    confidentiality: str | None = None,
) -> uuid.UUID:
    if transport not in _TRANSPORTS:
        raise ValueError(f"unknown transport {transport!r}")
    if purpose not in _PURPOSES:
        raise ValueError(f"unknown purpose {purpose!r}")
    if not _ENDPOINT_HASH.fullmatch(endpoint_hash):
        raise ValueError("endpoint_hash must be a sha256 hex digest, not a URL")
    if confidentiality is not None and confidentiality not in _CONFIDENTIALITY:
        raise ValueError(f"unknown confidentiality {confidentiality!r}")

    if confidentiality is None:
        sql = """
            insert into notification_channels
              (installation_id, name, transport, purpose, endpoint_hash)
            values (%s, %s, %s, %s, %s)
            returning id
            """
        params: tuple[object, ...] = (
            installation_id,
            name,
            transport,
            purpose,
            endpoint_hash,
        )
    else:
        sql = """
            insert into notification_channels
              (installation_id, name, transport, purpose, endpoint_hash, confidentiality)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """
        params = (
            installation_id,
            name,
            transport,
            purpose,
            endpoint_hash,
            confidentiality,
        )

    with connection() as conn:
        row = conn.execute(sql, params).fetchone()
    assert row is not None
    return uuid.UUID(str(row["id"]))
