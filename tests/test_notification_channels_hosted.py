"""Hosted notification_channels: operator-declared confidentiality, no webhook URLs."""

from __future__ import annotations

import pytest

from pr_reviewer.db.client import connection

ENDPOINT_HASH = "a" * 64


def test_hosted_notification_channel_defaults_confidentiality_to_restricted() -> None:
    from pr_reviewer.control_plane.notification_channels import declare_notification_channel
    from pr_reviewer.control_plane.repository_policy import register_installation

    register_installation(9101, "acme")
    channel_id = declare_notification_channel(
        installation_id=9101,
        name="ops-alerts",
        transport="slack",
        purpose="security_alert",
        endpoint_hash=ENDPOINT_HASH,
    )
    with connection() as conn:
        row = conn.execute(
            "select confidentiality, purpose, transport from notification_channels where id = %s",
            (str(channel_id),),
        ).fetchone()
    assert row is not None
    assert row["confidentiality"] == "restricted"
    assert row["purpose"] == "security_alert"
    assert row["transport"] == "slack"


def test_hosted_insert_omitting_confidentiality_column_is_restricted() -> None:
    from pr_reviewer.control_plane.repository_policy import register_installation

    register_installation(9102, "acme")
    with connection() as conn:
        row = conn.execute(
            """
            insert into notification_channels
              (installation_id, name, transport, purpose, endpoint_hash)
            values (%s, %s, %s, %s, %s)
            returning confidentiality
            """,
            (9102, "unset-channel", "telegram", "review_ping", ENDPOINT_HASH),
        ).fetchone()
    assert row is not None
    assert row["confidentiality"] == "restricted"


def test_hosted_notification_channels_cannot_store_a_webhook_url() -> None:
    from pr_reviewer.control_plane.notification_channels import declare_notification_channel
    from pr_reviewer.control_plane.repository_policy import register_installation

    register_installation(9103, "acme")
    with pytest.raises(ValueError):
        declare_notification_channel(
            installation_id=9103,
            name="bad",
            transport="slack",
            purpose="security_alert",
            endpoint_hash="https://hooks.slack.com/services/T00/B00/xxx",
        )
