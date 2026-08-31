"""Two jobs must not share an ordinary channel."""

from __future__ import annotations

from collections.abc import Sequence

from pr_reviewer.contracts.notification import NotificationChannel


class ChannelIsolationError(ValueError):
    """A security alert and a review ping share a channel that is not restricted."""


def assert_job_isolation(channels: Sequence[NotificationChannel]) -> None:
    grouped: dict[str, list[NotificationChannel]] = {}
    for channel in channels:
        grouped.setdefault(channel.id, []).append(channel)
    for channel_id, group in grouped.items():
        purposes = {item.purpose for item in group}
        if purposes != {"security_alert", "review_ping"}:
            continue
        if any(item.confidentiality != "restricted" for item in group):
            raise ChannelIsolationError(
                f"channel {channel_id} cannot carry both a security alert and a review ping "
                "unless it is marked restricted"
            )
