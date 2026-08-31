"""Fan-out with an injected send callable. No connectors or db imports."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pr_reviewer.contracts.notification import NotificationChannel, NotificationPreview


class RestrictedContentRefused(ValueError):
    """Restricted content was aimed at an ordinary channel. Not downgraded."""


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error_kind: str | None = None


@dataclass(frozen=True)
class ChannelDelivery:
    channel_id: str
    ok: bool
    error_kind: str | None = None


@dataclass(frozen=True)
class FanOutResult:
    deliveries: tuple[ChannelDelivery, ...]


SendFn = Callable[[NotificationChannel, NotificationPreview], SendResult]


def dispatch_notifications(
    preview: NotificationPreview,
    channels: Sequence[NotificationChannel],
    send: SendFn,
    *,
    idempotency_key: str,
    seen_keys: set[tuple[str, str]] | None = None,
) -> FanOutResult:
    if preview.confidentiality == "restricted":
        ordinary = [channel for channel in channels if channel.confidentiality != "restricted"]
        if ordinary:
            raise RestrictedContentRefused(
                "restricted content cannot be sent to an ordinary channel"
            )

    remembered = seen_keys if seen_keys is not None else set()
    deliveries: list[ChannelDelivery] = []
    for channel in channels:
        key = (idempotency_key, channel.id)
        if channel.revoked:
            deliveries.append(ChannelDelivery(channel.id, ok=False, error_kind="revoked"))
            continue
        if key in remembered:
            deliveries.append(ChannelDelivery(channel.id, ok=True, error_kind="duplicate"))
            continue
        try:
            result = send(channel, preview)
        except Exception:
            deliveries.append(
                ChannelDelivery(channel.id, ok=False, error_kind="delivery_failed")
            )
            continue
        if result.ok:
            remembered.add(key)
            deliveries.append(ChannelDelivery(channel.id, ok=True, error_kind=None))
        else:
            deliveries.append(
                ChannelDelivery(
                    channel.id,
                    ok=False,
                    error_kind=result.error_kind or "delivery_failed",
                )
            )
    return FanOutResult(deliveries=tuple(deliveries))
